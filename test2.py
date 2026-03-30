import dill
from psana import DataSource

with open("graph.dill", "rb") as f:
    graph_worker = dill.load(f)
with open("graph.dill", "rb") as f:
    graph_localCollector = dill.load(f)
with open("graph.dill", "rb") as f:
    graph_globalCollector = dill.load(f)

graph_worker.compile()
graph_localCollector.compile()
graph_globalCollector.compile()

ds = DataSource(exp='rix101331225', run=156)  # bad
run = next(ds.runs())

opal = run.Detector('c_atmopal')
piranha = run.Detector('c_piranha')
timing = run.Detector('timing')

for c,evt in enumerate(run.events()):
    img = opal.raw.image(evt)
    evt_codes = timing.raw.eventcodes(evt)

    has_opal = img is not None

    if has_opal:
        print(f"event: {c} opal: {has_opal} {evt_codes[272]} {evt_codes[273]}")

        worker = graph_worker({'c_atmopal:raw:image': img, 'timing:raw:eventcodes': evt_codes}, color='worker')
        print("worker:", worker)

        localCollector = graph_localCollector(worker, color='localCollector')
        print("localCollector:", localCollector)

        globalCollector = graph_globalCollector(localCollector, color='globalCollector')
        print("globalCollector:", globalCollector)

    if c > 100 and c % 100 == 0:
        print("HEARTBEAT:", c)
        graph_worker.heartbeat_finished()
        graph_localCollector.heartbeat_finished()
        graph_globalCollector.heartbeat_finished()

    if c > 700:
        break
