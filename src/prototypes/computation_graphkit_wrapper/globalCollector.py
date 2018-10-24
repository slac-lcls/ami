import dill
from multiprocessing import Process, Queue


def run_global_collector(local_collector_queue):

    with open('graph.dat', 'rb') as f:
        graph = dill.load(f)

    while True:
        results = []
        collector_id = local_collector_queue.get()
        with open('localCollector%d.dat' % collector_id, 'rb') as f:
            results.append(dill.load(f))

        res = graph({'d': results}, color='globalCollector')
        print("Global Collector collecting local collector %d results. Total %s" % (collector_id, res))


if __name__ == '__main__':
    local_collector_queue = Queue()
    local_collector_queue.put(1)
    local_collector_queue.put(2)
    p = Process(target=run_global_collector, args=(local_collector_queue,))
    p.start()
    p.join()
