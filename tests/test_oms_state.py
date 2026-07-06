"""Order state machine tests, including hypothesis property tests over
legal/illegal transition sequences (§4.5 acceptance)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from qt.oms.state import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    OrderRecord,
    OrderState,
)


def order(quantity: int = 10) -> OrderRecord:
    return OrderRecord(client_order_id="QT-test", symbol="MES", quantity=quantity)


def test_happy_path_ack_partial_fill() -> None:
    record = order()
    record.transition(OrderState.ACKED)
    record.transition(OrderState.PARTIAL, fill_quantity=4)
    record.transition(OrderState.PARTIAL, fill_quantity=3)
    record.transition(OrderState.FILLED, fill_quantity=3)
    assert record.filled_quantity == 10
    assert record.is_terminal
    assert record.history == [
        OrderState.PENDING_NEW,
        OrderState.ACKED,
        OrderState.PARTIAL,
        OrderState.PARTIAL,
        OrderState.FILLED,
    ]


def test_fill_before_ack_is_legal() -> None:
    record = order(1)
    record.transition(OrderState.FILLED, fill_quantity=1)  # IBKR can do this
    assert record.is_terminal


def test_cancel_after_partial_keeps_fills() -> None:
    record = order()
    record.transition(OrderState.PARTIAL, fill_quantity=4)
    record.transition(OrderState.CANCELLED)
    assert record.filled_quantity == 4
    assert record.is_terminal


def test_unknown_resolves_after_reconnect() -> None:
    record = order()
    record.transition(OrderState.ACKED)
    record.transition(OrderState.UNKNOWN)  # gateway died
    record.transition(OrderState.FILLED, fill_quantity=10)  # reconnect resolution
    assert record.is_terminal


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
def test_terminal_states_absorb(terminal: OrderState) -> None:
    record = order()
    fill = record.quantity if terminal is OrderState.FILLED else 0
    record.transition(terminal, fill_quantity=fill)
    for target in OrderState:
        with pytest.raises(IllegalTransitionError, match="illegal transition"):
            record.transition(target)


def test_overfill_rejected() -> None:
    record = order(2)
    with pytest.raises(IllegalTransitionError, match="FILLED with cumulative"):
        record.transition(OrderState.FILLED, fill_quantity=3)


def test_partial_reaching_full_quantity_rejected() -> None:
    record = order(2)
    with pytest.raises(IllegalTransitionError, match="should be FILLED"):
        record.transition(OrderState.PARTIAL, fill_quantity=2)


def test_fill_on_non_fill_state_rejected() -> None:
    record = order()
    with pytest.raises(IllegalTransitionError, match="cannot carry a fill"):
        record.transition(OrderState.ACKED, fill_quantity=1)


def test_rejected_after_ack_is_illegal() -> None:
    record = order()
    record.transition(OrderState.ACKED)
    with pytest.raises(IllegalTransitionError):
        record.transition(OrderState.REJECTED)  # broker acked it; late reject = UNKNOWN path


# ---------------------------------------------------------------------------
# Property tests over transition sequences
# ---------------------------------------------------------------------------

_EVENTS = st.tuples(st.sampled_from(list(OrderState)), st.integers(min_value=0, max_value=4))


@settings(max_examples=300, deadline=None)
@given(quantity=st.integers(min_value=1, max_value=12), events=st.lists(_EVENTS, max_size=12))
def test_random_sequences_preserve_invariants(
    quantity: int, events: list[tuple[OrderState, int]]
) -> None:
    """Whatever sequence the broker throws at us: either every step is legal
    and all invariants hold, or the machine raises AT the illegal step and
    state is unchanged from before that step."""
    record = OrderRecord(client_order_id="QT-prop", symbol="MES", quantity=quantity)
    for state, fill in events:
        before = (record.state, record.filled_quantity)
        try:
            record.transition(state, fill_quantity=fill)
        except IllegalTransitionError:
            assert (record.state, record.filled_quantity) == before  # atomic failure
            break
        assert record.state is state
        assert 0 <= record.filled_quantity <= record.quantity
        assert record.state is not OrderState.FILLED or record.filled_quantity == record.quantity
        assert record.state is not OrderState.PARTIAL or record.filled_quantity < record.quantity
        assert record.history[-1] is state


@settings(max_examples=200, deadline=None)
@given(events=st.lists(_EVENTS, min_size=1, max_size=12))
def test_filled_quantity_is_monotone(events: list[tuple[OrderState, int]]) -> None:
    record = OrderRecord(client_order_id="QT-mono", symbol="MES", quantity=8)
    seen = [0]
    for state, fill in events:
        try:
            record.transition(state, fill_quantity=fill)
        except IllegalTransitionError:
            break
        seen.append(record.filled_quantity)
    assert seen == sorted(seen)


@settings(max_examples=200, deadline=None)
@given(events=st.lists(_EVENTS, min_size=1, max_size=12))
def test_every_reached_state_is_reachable_per_table(
    events: list[tuple[OrderState, int]],
) -> None:
    record = OrderRecord(client_order_id="QT-table", symbol="MES", quantity=8)
    previous = record.state
    for state, fill in events:
        try:
            record.transition(state, fill_quantity=fill)
        except IllegalTransitionError:
            break
        assert state in LEGAL_TRANSITIONS[previous]
        previous = state
