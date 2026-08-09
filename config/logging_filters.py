import logging
import re


class SanitizePIIFilter(logging.Filter):
    phone = re.compile(r"(?<!\d)(?:\+?51)?\d{9}(?!\d)")
    token = re.compile(r"(?i)(access[_ -]?token|api[_ -]?key|secret)(\s*[=:]\s*)([^\s,;]+)")

    def filter(self, record):
        message = record.getMessage()
        message = self.phone.sub("***PHONE", message)
        message = self.token.sub(r"\1\2***", message)
        record.msg = message
        record.args = ()
        return True
