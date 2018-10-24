import dill
import time
from multiprocessing import Process, Queue


def run_local_collector(worker_queue, output_queue, workers_per_collector, collector_id):

    with open('graph.dat', 'rb') as f:
        graph = dill.load(f)

    workers = [False]*workers_per_collector
    w = 0

    while True:
        results = []
        worker_id = worker_queue.get()
        with open('worker%d.dat' % worker_id, 'rb') as f:
            results.append(dill.load(f))

        workers[w] = True
        w = (w + 1) % workers_per_collector

        res = graph({'c': results}, color='localCollector')
        print("Local Collector %d collecting worker %d results. Total: %s" % (collector_id, worker_id, res))

        with open('localCollector%d.dat' % collector_id, 'wb') as f:
            dill.dump(res, f)

        if all(workers):
            time.sleep(0.25)
            output_queue.put(collector_id)
            workers = [False]*workers_per_collector


if __name__ == '__main__':
    workers_per_collector = 2
    worker_queue = Queue()
    output_queue = Queue()
    worker_queue.put(1)
    worker_queue.put(2)
    p1 = Process(target=run_local_collector, args=(worker_queue, output_queue, workers_per_collector, 1))
    p1.start()
    worker_queue2 = Queue()
    worker_queue2.put(3)
    worker_queue2.put(4)
    p2 = Process(target=run_local_collector, args=(worker_queue2, output_queue, workers_per_collector, 2))
    p2.start()
