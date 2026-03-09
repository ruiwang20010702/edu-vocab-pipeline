"""所有枚举定义."""

import enum


class QcStatus(str, enum.Enum):
    """内容项质检状态."""

    PENDING = "pending"
    LAYER1_PASSED = "layer1_passed"
    LAYER1_FAILED = "layer1_failed"
    LAYER2_PASSED = "layer2_passed"
    LAYER2_FAILED = "layer2_failed"
    APPROVED = "approved"
    REJECTED = "rejected"


class QcRunStatus(str, enum.Enum):
    """质检运行状态."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AiStrategy(str, enum.Enum):
    """AI 校验策略."""

    PER_RULE = "per_rule"
    UNIFIED = "unified"


class ReviewReason(str, enum.Enum):
    """审核原因."""

    LAYER1_FAILED = "layer1_failed"
    LAYER2_FAILED = "layer2_failed"
    SAMPLING = "sampling"


class ReviewStatus(str, enum.Enum):
    """审核项状态."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class ReviewResolution(str, enum.Enum):
    """审核决议."""

    APPROVED = "approved"
    REGENERATE = "regenerate"
    MANUAL_EDIT = "manual_edit"


class ContentDimension(str, enum.Enum):
    """内容维度."""

    MEANING = "meaning"
    PHONETIC = "phonetic"
    SYLLABLE = "syllable"
    CHUNK = "chunk"
    SENTENCE = "sentence"
    MNEMONIC_ROOT_AFFIX = "mnemonic_root_affix"
    MNEMONIC_WORD_IN_WORD = "mnemonic_word_in_word"
    MNEMONIC_SOUND_MEANING = "mnemonic_sound_meaning"
    MNEMONIC_EXAM_APP = "mnemonic_exam_app"


class MnemonicType(str, enum.Enum):
    """助记类型."""

    ROOT_AFFIX = "词根词缀"
    WORD_IN_WORD = "词中词"
    SOUND_MEANING = "音义联想"
    EXAM_APPLICATION = "考试应用"


# 所有助记维度名集合，方便各处判断
MNEMONIC_DIMENSIONS = frozenset({
    ContentDimension.MNEMONIC_ROOT_AFFIX.value,
    ContentDimension.MNEMONIC_WORD_IN_WORD.value,
    ContentDimension.MNEMONIC_SOUND_MEANING.value,
    ContentDimension.MNEMONIC_EXAM_APP.value,
})


class UserRole(str, enum.Enum):
    """用户角色."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class BatchStatus(str, enum.Enum):
    """批次状态."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class PromptStatus(str, enum.Enum):
    """Prompt 版本状态."""

    DRAFT = "draft"
    TESTING = "testing"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
