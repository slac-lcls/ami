import dill
import time
from multiprocessing import Process, Queue


def run_worker(input_queue, output_queue, worker_id):
    with open('graph.dat', 'rb') as f:
        graph = dill.load(f)

    while True:
        args = input_queue.get()
        res = graph(args, color='worker')
        print("Worker %d: %s" % (worker_id, res))

        with open('worker%d.dat' % worker_id, 'wb') as f:
            dill.dump(res, f)

        time.sleep(0.25)
        output_queue.put(worker_id)


if __name__ == '__main__':
    input_queue = Queue()
    output_queue = Queue()
    workers = 4
    for worker_id in range(1, workers+1):
        input_queue.put({'a': 1, 'b': 3})
        p = Process(target=run_worker, args=(input_queue, output_queue, worker_id,))
        p.start()
