import numpy as np
import pytest

pytest.importorskip("scipy")
pytest.importorskip("sympy")

import ami.graph_nodes as gn  # noqa: E402
from ami.flowchart.library.Scipy import FitProc  # noqa: E402


def test_curvefit_failure_raises_warning(monkeypatch):
    """A fit that doesn't converge is a per-event AMIWarning, not an empty return that later
    crashes networkfox and purges the graph."""
    import scipy.optimize

    def no_converge(*args, **kwargs):
        raise RuntimeError("Optimal parameters not found: Number of calls to function has reached maxfev = 1000.")

    monkeypatch.setattr(scipy.optimize, "curve_fit", no_converge)
    proc = FitProc(f="a*x + b", variables="x,a,b", p0="")
    with pytest.raises(gn.AMIWarning, match="Optimal parameters not found"):
        proc(np.arange(10, dtype=float))


def test_curvefit_bad_input_raises_warning():
    """Other fitting errors (e.g. NaNs in the data) are also per-event warnings."""
    proc = FitProc(f="a*x + b", variables="x,a,b", p0="")
    with pytest.raises(gn.AMIWarning):
        proc(np.array([1.0, np.nan, 3.0, 4.0]))


def test_curvefit_success():
    proc = FitProc(f="a*x + b", variables="x,a,b", p0="")
    x = np.arange(20, dtype=float)
    fx, popt, _ = proc(2 * x + 1)
    np.testing.assert_allclose(popt, [2, 1], atol=1e-6)
    np.testing.assert_allclose(fx, 2 * x + 1, atol=1e-6)


def test_curvefit_failure_in_graph_is_warning_not_error(monkeypatch):
    """Through networkfox the failed fit skips its outputs and is reported via graph.warnings(),
    attributed to the node, instead of raising (which would purge the graph on the worker)."""
    import scipy.optimize

    from ami.graphkit_wrapper import Graph

    def no_converge(*args, **kwargs):
        raise RuntimeError("Optimal parameters not found")

    monkeypatch.setattr(scipy.optimize, "curve_fit", no_converge)
    graph = Graph(name="fit")
    graph.add(
        gn.Map(
            name="CurveFit.0_operation",
            inputs=["y"],
            outputs=["CurveFit.0.fx", "CurveFit.0.p0", "CurveFit.0.pcov"],
            func=FitProc(f="a*x + b", variables="x,a,b", p0=""),
            parent="CurveFit.0",
        )
    )
    graph.compile(num_workers=1, num_local_collectors=1)
    # Graph.__call__ filters to the color's exported outputs (none here), so check the raw networkfox result
    result = graph.graphkit({"y": np.arange(10, dtype=float)}, color="worker")
    graph._accumulate_warnings()  # what Graph.__call__ does after each event

    assert "CurveFit.0.fx" not in result
    warnings = graph.warnings()
    assert len(warnings) == 1
    warning = next(iter(warnings.values()))
    assert isinstance(warning, gn.AMIWarning)
    assert warning.node_name == "CurveFit.0_operation"


def _flaky_fit_graph(monkeypatch, fail_on):
    """Graph with one CurveFit op whose fit fails on the calls listed in fail_on (0-based)."""
    import scipy.optimize

    from ami.graphkit_wrapper import Graph

    real_curve_fit = scipy.optimize.curve_fit
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        n = calls["n"]
        calls["n"] += 1
        if n in fail_on:
            raise RuntimeError("Optimal parameters not found")
        return real_curve_fit(*args, **kwargs)

    monkeypatch.setattr(scipy.optimize, "curve_fit", flaky)
    graph = Graph(name="fit")
    graph.add(
        gn.Map(
            name="CurveFit.0_operation",
            inputs=["y"],
            outputs=["CurveFit.0.fx", "CurveFit.0.p0", "CurveFit.0.pcov"],
            func=FitProc(f="a*x + b", variables="x,a,b", p0=""),
            parent="CurveFit.0",
        )
    )
    graph.compile(num_workers=1, num_local_collectors=1)
    return graph


def test_warning_survives_later_successful_event(monkeypatch):
    """networkfox resets warnings per call; Graph keeps them until the heartbeat reads them."""
    graph = _flaky_fit_graph(monkeypatch, fail_on={0})
    y = np.arange(10, dtype=float)
    assert "CurveFit.0.fx" not in graph.graphkit({"y": y}, color="worker")  # fails
    graph._accumulate_warnings()
    assert "CurveFit.0.fx" in graph.graphkit({"y": y}, color="worker")  # succeeds
    graph._accumulate_warnings()

    warnings = graph.warnings()
    assert list(warnings) == ["CurveFit.0_operation"]
    assert warnings["CurveFit.0_operation"].event_count == 1
    assert graph.warnings() == {}


def test_warning_event_count(monkeypatch):
    graph = _flaky_fit_graph(monkeypatch, fail_on={0, 2, 3})
    y = np.arange(10, dtype=float)
    for _ in range(5):
        graph({"y": y}, color="worker")
    assert graph.warnings()["CurveFit.0_operation"].event_count == 3
