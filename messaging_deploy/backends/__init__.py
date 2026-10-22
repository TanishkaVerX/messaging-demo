from .base import Backend
from .kafka import KafkaBackend
from .pulsar import PulsarBackend

BACKENDS: dict[str, type[Backend]] = {"pulsar": PulsarBackend, "kafka": KafkaBackend}
