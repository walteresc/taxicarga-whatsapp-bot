"""Un proveedor LLM falso para tests del orquestador: se le programa una cola de
respuestas (cada una = lista de function_calls, o un texto final)."""
import json
from types import SimpleNamespace


def _call(nombre, args, call_id):
    return SimpleNamespace(
        type="function_call", name=nombre, call_id=call_id,
        arguments=json.dumps(args),
        model_dump=lambda: {"type": "function_call", "name": nombre,
                            "call_id": call_id, "arguments": json.dumps(args)},
    )


class RespuestaFake:
    def __init__(self, *, calls=None, texto=""):
        cid = 0
        self.output = []
        for (n, a) in (calls or []):
            cid += 1
            self.output.append(_call(n, a, f"c{cid}"))
        self.output_text = texto
        self.usage = SimpleNamespace(input_tokens=10, output_tokens=5)


class ProviderFake:
    def __init__(self, guion):
        # guion: lista de dicts {calls: [(nombre, args), ...]} o {texto: "..."}
        self._guion = list(guion)
        self.llamadas = 0

    def generar_con_tools(self, messages, tools, *, max_output_tokens=1400):
        self.llamadas += 1
        if self._guion:
            paso = self._guion.pop(0)
        else:
            paso = {"texto": "Listo."}
        return RespuestaFake(calls=paso.get("calls"), texto=paso.get("texto", ""))
