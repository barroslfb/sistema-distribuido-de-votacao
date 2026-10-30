"""Utilitários de mensagens UTF-8 delimitadas por newline sobre TCP."""

COMMAND_JOIN = "JOIN"
COMMAND_VOTE = "VOTE"
COMMAND_SUCCESS = "SUCCESS"
COMMAND_ERROR = "ERROR"
COMMAND_UPDATE = "UPDATE"
COMMAND_END = "END"


class NewlineFramer:
    """Armazena fragmentos TCP e retorna mensagens UTF-8 completas."""

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data):
        """Adiciona bytes e retorna mensagens completas, sem o newline."""
        self._buffer.extend(data)
        messages = []
        while True:
            boundary = self._buffer.find(b"\n")
            if boundary < 0:
                break
            line = bytes(self._buffer[:boundary])
            del self._buffer[: boundary + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            messages.append(line.decode("utf-8"))
        return messages

    def finish(self):
        """Retorna a mensagem final sem delimitador, se houver."""
        if not self._buffer:
            return None
        message = bytes(self._buffer).decode("utf-8")
        self._buffer.clear()
        return message


def encode_message(message):
    """Codifica uma mensagem de texto em UTF-8 seguida por newline."""
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    if "\n" in message:
        raise ValueError("message cannot contain a newline")
    return (message + "\n").encode("utf-8")
