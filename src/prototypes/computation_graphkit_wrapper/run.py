from client import run_client
from worker import run_worker
from localCollector import run_local_collector
from globalCollector import run_global_collector
from multiprocessing import Process, Queue
from time import sleep
import os
import sys


def prompt(stdin, input_queue, workers=4):

    while True:
        print('a:')
        a = stdin.readline().strip()
        print('b:')
        b = stdin.readline().strip()
        args = {'a': float(a), 'b': float(b)}
        for i in range(0, workers):
            input_queue.put(args)
        sleep(1)


if __name__ == '__main__':
    run_client()
    workers = 4
    local_collectors = int(workers/2)
    workers_per_collector = int(workers/local_collectors)
    input_queue = Queue()
    local_collector_queue1 = Queue()
    local_collector_queue2 = Queue()
    global_collector_queue = Queue()

    newstdin = os.fdopen(os.dup(sys.stdin.fileno()))
    prompt_proc = Process(target=prompt, args=(newstdin, input_queue, workers))
    prompt_proc.start()

    worker_procs = []

    for worker_id in range(1, workers+1):
        if 1 <= worker_id <= 2:
            output_queue = local_collector_queue1
        else:
            output_queue = local_collector_queue2
        worker = Process(target=run_worker, args=(input_queue, output_queue, worker_id))
        worker_procs.append(worker)
        worker.start()

    local_collector_procs = []

    for local_collector_id in range(1, local_collectors+1):
        if local_collector_id == 1:
            input_queue = local_collector_queue1
        else:
            input_queue = local_collector_queue2
        local_collector = Process(target=run_local_collector,
                                  args=(input_queue, global_collector_queue, workers_per_collector, local_collector_id))
        local_collector_procs.append(local_collector)
        local_collector.start()

    global_collector_proc = Process(target=run_global_collector, args=(global_collector_queue,))
    global_collector_proc.start()

    prompt_proc.join()

    for proc in worker_procs:
        proc.join()

    for proc in local_collector_procs:
        proc.join()

    global_collector_proc.join()
