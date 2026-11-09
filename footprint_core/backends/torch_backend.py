"""Linux/Windows backend: transformers + peft (CUDA if available, else CPU)."""
import json, os

from .. import adapters, config


def train():
    from datasets import load_dataset
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer
    ds = load_dataset("json", data_files={"train": os.path.join(config.DATA, "train.jsonl"),
                                          "valid": os.path.join(config.DATA, "valid.jsonl")})
    v, out = adapters.new_version()
    iters = int(config.resolve_iters())
    every = max(25, iters // 10)
    trainer = SFTTrainer(
        model=config.MODEL,
        args=SFTConfig(output_dir=out, max_steps=iters, per_device_train_batch_size=config.BATCH,
                       gradient_checkpointing=True, max_length=4096, logging_steps=25, report_to=[],
                       learning_rate=float(config.LEARNING_RATE), assistant_only_loss=True,  # = mlx --mask-prompt
                       eval_strategy="steps", eval_steps=every, save_strategy="steps", save_steps=every,
                       load_best_model_at_end=True, metric_for_best_model="eval_loss", save_total_limit=2),
        train_dataset=ds["train"], eval_dataset=ds["valid"],
        peft_config=LoraConfig(r=config.LORA_RANK, lora_alpha=config.LORA_ALPHA, lora_dropout=0.05,
                               target_modules="all-linear"))
    trainer.train()
    trainer.save_model(out)  # best checkpoint (load_best_model_at_end) = early stop
    adapters.finish(v, {"format": "native-v2", "iters": iters, "test_loss": evaluate(out),
                        "val_loss": trainer.state.best_metric, "rank": config.LORA_RANK})


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
