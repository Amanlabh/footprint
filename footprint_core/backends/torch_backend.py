"""Linux/Windows backend: transformers + peft (CUDA if available, else CPU)."""
import json, os

from .. import adapters, config


def train(force_ckpt=False):
    """Same recipe as the MLX backend: last-half layers, fitted max length, auto grad checkpoint,
    early stop only with a real validation set, resume from the last checkpoint. The HF progress bar shows ETA."""
    import glob
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoConfig, AutoTokenizer, TrainerCallback
    from trl import SFTConfig, SFTTrainer
    ds = load_dataset("json", data_files={"train": os.path.join(config.DATA, "train.jsonl"),
                                          "valid": os.path.join(config.DATA, "valid.jsonl")})
    tok = AutoTokenizer.from_pretrained(config.MODEL)
    seq = config.fit_seq([len(tok.apply_chat_template(e["messages"], tools=e.get("tools"), tokenize=True))
                          for split in ds.values() for e in split])
    total = AutoConfig.from_pretrained(config.MODEL).num_hidden_layers
    layers = config.lora_layers(total)
    iters = int(config.resolve_iters())
    every = max(25, iters // 10)
    sig = {"model": config.MODEL, "data": adapters.data_hash(), "rank": config.LORA_RANK, "layers": layers,
           "seq": seq, "iters": iters, "lr": config.LEARNING_RATE, "batch": config.BATCH}
    v, out, prog = adapters.start(sig)
    adapters.save_progress(out, prog or {"sig": sig, "iters": iters, "done": 0})

    class Progress(TrainerCallback):  # each checkpoint makes the run resumable by the next `footprint train`
        def on_save(self, args, state, control, **kw):
            adapters.save_progress(out, {"sig": sig, "iters": iters, "done": state.global_step})
    ckpt = force_ckpt or config.grad_ckpt(seq, layers)
    early = len(ds["valid"]) >= config.MIN_EVAL
    print(f"training {v}: {iters} steps · last {layers}/{total} layers · max length {seq} · "
          f"grad checkpoint {'on' if ckpt else 'off'}" + ("" if early else " · early stop off (validation too small)"))
    trainer = SFTTrainer(
        model=config.MODEL,
        args=SFTConfig(output_dir=out, max_steps=iters, per_device_train_batch_size=config.BATCH,
                       gradient_checkpointing=ckpt, max_length=seq, logging_steps=5, report_to=[],
                       learning_rate=float(config.LEARNING_RATE), assistant_only_loss=True,  # = mlx --mask-prompt
                       eval_strategy="steps", eval_steps=every, save_strategy="steps", save_steps=every,
                       load_best_model_at_end=early, metric_for_best_model="eval_loss", save_total_limit=2),
        train_dataset=ds["train"], eval_dataset=ds["valid"], callbacks=[Progress()],
        peft_config=LoraConfig(r=config.LORA_RANK, lora_alpha=config.LORA_ALPHA, lora_dropout=0.05,
                               target_modules="all-linear", layers_to_transform=list(range(total - layers, total))))
    try:
        trainer.train(resume_from_checkpoint=bool(glob.glob(os.path.join(out, "checkpoint-*"))))
    except RuntimeError as e:
        if config.OOM.search(str(e)) and not ckpt:
            print("out of memory — retrying with grad checkpoint on")
            return train(force_ckpt=True)
        raise
    trainer.save_model(out)  # best checkpoint when early (load_best_model_at_end), else the last step
    os.remove(os.path.join(out, "progress.json"))
    adapters.finish(v, {"format": "native-v2", "iters": iters, "test_loss": evaluate(out), "early_stop": early,
                        "val_loss": trainer.state.best_metric, "rank": config.LORA_RANK, "layers": layers, "seq": seq})


def evaluate(path=None):
    import math
    from datasets import load_dataset
    from peft import PeftModel
    from transformers import AutoModelForCausalLM
    from trl import SFTConfig, SFTTrainer
    if not path and not config.has_adapter():
        raise SystemExit("no trained adapter. run: footprint train")
    ds = load_dataset("json", data_files={"test": config.ensure_test()})
    base = AutoModelForCausalLM.from_pretrained(config.MODEL, torch_dtype="auto", device_map="auto")
    path = path or config.ADAPTERS
    model = PeftModel.from_pretrained(base, path)
    trainer = SFTTrainer(model=model, eval_dataset=ds["test"],
                         args=SFTConfig(output_dir=path, max_length=4096, assistant_only_loss=True,
                                        per_device_eval_batch_size=config.BATCH, report_to=[]))
    loss = trainer.evaluate()["eval_loss"]
    print(f"Test loss {loss:.3f}, Test ppl {math.exp(loss):.3f}")
    return round(loss, 3)


def serve():
    import torch
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(config.MODEL)
    model = AutoModelForCausalLM.from_pretrained(config.MODEL, torch_dtype="auto", device_map="auto")
    if config.has_adapter():
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, config.ADAPTERS)
    else:
        print("(no adapter yet — serving base model; run train first for footprint behavior)")
    model.eval()

    def generate(messages, max_tokens, temperature):
        ids = tok.apply_chat_template(messages, add_generation_prompt=True,
                                      return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=max_tokens, do_sample=temperature > 0,
                                 temperature=max(temperature, 1e-3),
                                 pad_token_id=tok.eos_token_id)
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, ctype="application/json"):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/v1/models"):
                self._json({"object": "list", "data": [{"id": "footprint", "object": "model"}]})
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path.rstrip("/") != "/v1/chat/completions":
                self.send_error(404)
                return
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = generate(req.get("messages", []), req.get("max_tokens") or 1024,
                            req.get("temperature") if req.get("temperature") is not None else 0.7)
            if req.get("stream"):
                # ponytail: whole answer as one SSE chunk; true token streaming if UX needs it
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for payload in (
                        {"id": "fp", "object": "chat.completion.chunk", "model": "footprint",
                         "choices": [{"index": 0, "delta": {"role": "assistant", "content": text},
                                      "finish_reason": None}]},
                        {"id": "fp", "object": "chat.completion.chunk", "model": "footprint",
                         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}):
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                self._json({"id": "fp", "object": "chat.completion", "model": "footprint",
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                         "finish_reason": "stop"}]})

        def log_message(self, *a):
            pass

    print(f"OpenAI-compatible API: http://127.0.0.1:{config.PORT}/v1  (model name: footprint)\n"
          f"device: {'cuda' if torch.cuda.is_available() else 'cpu'}")
    ThreadingHTTPServer(("127.0.0.1", int(config.PORT)), Handler).serve_forever()
