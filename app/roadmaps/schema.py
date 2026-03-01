import enum


class PhaseEnum(str, enum.Enum):
    T0_30M = "T0_30M"
    T30M_2H = "T30M_2H"
    H2_24H = "H2_24H"
    D1_7 = "D1_7"
    MONITORING = "MONITORING"


class ItemTypeEnum(str, enum.Enum):
    STRATEGY = "strategy"
    TACTIC = "tactic"
    MESSAGE = "message"
    MONITORING = "monitoring"


class PriorityEnum(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class StatusEnum(str, enum.Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    BLOCKED = "blocked"


class CreatedByEnum(str, enum.Enum):
    AI = "ai"
    USER = "user"