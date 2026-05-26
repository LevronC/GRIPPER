import os
import sys
from redis import Redis
from rq import Worker, Queue

# Ensure the root backend folder is in pythonpath
sys.path.insert(0, os.path.realpath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.core.config import settings

listen = ['default']

def run_worker():
    # Connect to local Redis queue using URL configured in settings
    redis_conn = Redis.from_url(settings.REDIS_URL)
    queues = [Queue(name, connection=redis_conn) for name in listen]
    worker = Worker(queues, connection=redis_conn)
    print(f"[*] Gripper RQ Worker starting. Listening on: {listen} (Redis: {settings.REDIS_URL})")
    worker.work()

if __name__ == '__main__':
    run_worker()

