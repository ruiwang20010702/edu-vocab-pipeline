"""状态机转换测试 — validate_qc_transition + QC_TERMINAL_STATUSES."""

import pytest
from vocab_qc.core.models.enums import (
    QC_TERMINAL_STATUSES,
    QcStatus,
    validate_qc_transition,
)

# ---------------------------------------------------------------------------
# QC_TERMINAL_STATUSES
# ---------------------------------------------------------------------------


def test_terminal_statuses_contains_approved():
    assert QcStatus.APPROVED.value in QC_TERMINAL_STATUSES


def test_terminal_statuses_contains_rejected():
    assert QcStatus.REJECTED.value in QC_TERMINAL_STATUSES


def test_terminal_statuses_does_not_contain_pending():
    assert QcStatus.PENDING.value not in QC_TERMINAL_STATUSES


def test_terminal_statuses_does_not_contain_layer1_passed():
    assert QcStatus.LAYER1_PASSED.value not in QC_TERMINAL_STATUSES


def test_terminal_statuses_is_frozenset():
    assert isinstance(QC_TERMINAL_STATUSES, frozenset)


# ---------------------------------------------------------------------------
# 合法转换
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current, target",
    [
        # PENDING 可到三个目标
        (QcStatus.PENDING, QcStatus.LAYER1_PASSED),
        (QcStatus.PENDING, QcStatus.LAYER1_FAILED),
        (QcStatus.PENDING, QcStatus.REJECTED),
        # LAYER1_PASSED 可到 Layer2
        (QcStatus.LAYER1_PASSED, QcStatus.LAYER2_PASSED),
        (QcStatus.LAYER1_PASSED, QcStatus.LAYER2_FAILED),
        # LAYER1_FAILED 可回 PENDING（重试）
        (QcStatus.LAYER1_FAILED, QcStatus.PENDING),
        # LAYER2_PASSED → APPROVED（终态之路）
        (QcStatus.LAYER2_PASSED, QcStatus.APPROVED),
        # LAYER2_FAILED 可回 PENDING（重试）
        (QcStatus.LAYER2_FAILED, QcStatus.PENDING),
        # REJECTED 可回 PENDING（申诉 / 重新处理）
        (QcStatus.REJECTED, QcStatus.PENDING),
    ],
)
def test_valid_transition_returns_true(current: QcStatus, target: QcStatus):
    assert validate_qc_transition(current, target) is True


# ---------------------------------------------------------------------------
# 非法转换
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current, target",
    [
        # 终态 APPROVED 不能再转换
        (QcStatus.APPROVED, QcStatus.LAYER1_PASSED),
        (QcStatus.APPROVED, QcStatus.LAYER2_PASSED),
        (QcStatus.APPROVED, QcStatus.PENDING),
        (QcStatus.APPROVED, QcStatus.REJECTED),
        # 终态 REJECTED 只能回 PENDING，其余非法
        (QcStatus.REJECTED, QcStatus.APPROVED),
        (QcStatus.REJECTED, QcStatus.LAYER1_PASSED),
        # PENDING 不能直接跳到 Layer2
        (QcStatus.PENDING, QcStatus.LAYER2_PASSED),
        (QcStatus.PENDING, QcStatus.LAYER2_FAILED),
        (QcStatus.PENDING, QcStatus.APPROVED),
        # LAYER1_PASSED 不能跳过 Layer2 直接 APPROVED
        (QcStatus.LAYER1_PASSED, QcStatus.APPROVED),
        (QcStatus.LAYER1_PASSED, QcStatus.PENDING),
        # LAYER2_PASSED 不能降级
        (QcStatus.LAYER2_PASSED, QcStatus.LAYER1_PASSED),
        (QcStatus.LAYER2_PASSED, QcStatus.PENDING),
        # 自我转换均非法
        (QcStatus.PENDING, QcStatus.PENDING),
        (QcStatus.LAYER1_PASSED, QcStatus.LAYER1_PASSED),
        (QcStatus.APPROVED, QcStatus.APPROVED),
    ],
)
def test_invalid_transition_returns_false(current: QcStatus, target: QcStatus):
    assert validate_qc_transition(current, target) is False


# ---------------------------------------------------------------------------
# 边界：所有终态的出边为空
# ---------------------------------------------------------------------------


def test_approved_has_no_valid_outgoing_transitions():
    valid_targets = [
        t for t in QcStatus if validate_qc_transition(QcStatus.APPROVED, t)
    ]
    assert valid_targets == []
