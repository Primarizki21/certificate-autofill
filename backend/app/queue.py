"""RabbitMQ has been removed from this prototype variant.

This file is kept only so old imports fail with a clear message if any stale
code path still tries to use a queue.
"""


def publish_job(*args, **kwargs):
    raise RuntimeError("RabbitMQ sudah dihapus. Gunakan BackgroundTasks atau DB polling worker.")


def publish_dlq(*args, **kwargs):
    raise RuntimeError("RabbitMQ sudah dihapus. Gunakan tabel extraction_jobs.error_message untuk error job.")
