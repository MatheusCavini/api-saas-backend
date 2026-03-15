import logging

class BracketFormatter(logging.Formatter):
    """Custom formatter to wrap variables in brackets BEFORE applying padding."""
    def format(self, record):
        # Cria novas variáveis com os colchetes já aplicados
        record.level_bracket = f"[{record.levelname}]"
        record.name_bracket = f"[{record.name}]"
        
        # Passa para o formatador padrão do Python fazer o resto
        return super().format(record)