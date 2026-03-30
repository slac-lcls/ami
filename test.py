from psana import DataSource

# ds = DataSource(exp='rix101259825', run=11)  # good
ds = DataSource(exp='rix101331225', run=156)  # bad
run = next(ds.runs())

opal = run.Detector('c_atmopal')
piranha = run.Detector('c_piranha')
timing = run.Detector('timing')

for c,evt in enumerate(run.events()):
    img = opal.raw.image(evt)
    wave = piranha.raw.raw(evt)
    evt_codes = timing.raw.eventcodes(evt)

    has_opal = img is not None
    has_wave = wave is not None

    if has_opal:
        print(f"event: {c} opal: {has_opal} {evt_codes[272]} {evt_codes[273]}")

    # print(f"event: {c} opal: {has_opal} piranha: {has_wave} {evt_codes[272]} {evt_codes[273]}")
