"""Linux/Windows backend: transformers + peft (CUDA if available, else CPU)."""
import json, os

from .. import config


def train():
    from datasets import load_dataset
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer
    ds = load_dataset("json", data_files={"train": os.path.join(config.DATA, "train.jsonl"),
                                          "valid": os.path.join(config.DATA, "valid.jsonl")})
    trainer = SFTTrainer(
        model=config.MODEL,
        args=SFTConfig(output_dir=config.ADAPTERS, max_steps=int(config.ITERS),
                       per_device_train_batch_size=1, gradient_checkpointing=True,
                       max_length=4096, logging_steps=25, report_to=[]),
        train_dataset=ds["train"], eval_dataset=ds["valid"],
        peft_config=LoraConfig(r=8, lora_alpha=16, target_modules="all-linear"))
    trainer.train()
    trainer.save_model(config.ADAPTERS)
    print(f"adapter saved -> {config.ADAPTERS}")


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
