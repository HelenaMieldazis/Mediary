"""Servidor HTTP falso da API da Anthropic, para testar a IA sem gastar créditos.

Responde POST /v1/messages no mesmo formato da API real. O teste enfileira as
respostas (JSON que o "modelo" devolve, ou um status de erro) e depois confere
o que o backend enviou (modelo, output_config, ausência de temperature, ausência
de nome/e-mail do paciente etc.).

Uso:
    with ServidorFalsoAnthropic() as srv:
        os.environ["ANTHROPIC_BASE_URL"] = srv.url
        srv.responder_json({"tipo": "DOR", ...})
        ... chama o backend ...
        srv.requisicoes[-1]["body"]
"""
import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ServidorFalsoAnthropic:
    def __init__(self):
        self.requisicoes = []
        self._fila = deque()
        self._trava = threading.Lock()
        servidor = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencioso
                pass

            def do_POST(self):
                tamanho = int(self.headers.get("content-length", 0))
                corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                with servidor._trava:
                    servidor.requisicoes.append({"path": self.path, "headers": dict(self.headers),
                                                 "body": corpo})
                    item = servidor._fila.popleft() if servidor._fila else ("erro", 500, None)
                if self.path.split("?")[0] != "/v1/messages":
                    return self._enviar(404, {"type": "error", "error": {"type": "not_found_error",
                                                                         "message": "não existe"}})
                tipo, status, dado = item
                if tipo == "erro":
                    return self._enviar(status, {"type": "error", "error": {
                        "type": "api_error" if status >= 500 else "invalid_request_error",
                        "message": "erro simulado"}}, nao_repetir=True)
                texto = dado if isinstance(dado, str) else json.dumps(dado, ensure_ascii=False)
                self._enviar(200, {
                    "id": f"msg_falso_{len(servidor.requisicoes)}", "type": "message",
                    "role": "assistant", "model": corpo.get("model"),
                    "content": [{"type": "text", "text": texto}],
                    "stop_reason": status, "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 10},
                })

            def _enviar(self, status, obj, nao_repetir=False):
                dados = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(dados)))
                if nao_repetir:
                    self.send_header("x-should-retry", "false")
                self.end_headers()
                self.wfile.write(dados)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    # ── fila de respostas ──
    def responder_json(self, dado, stop_reason="end_turn"):
        self._fila.append(("ok", stop_reason, dado))

    def responder_erro(self, status=500):
        self._fila.append(("erro", status, None))

    def limpar(self):
        self._fila.clear()
        self.requisicoes.clear()

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
