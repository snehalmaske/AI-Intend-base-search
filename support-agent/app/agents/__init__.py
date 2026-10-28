from .base import BaseAgent, StepResult
from .email import EmailAgent
from .intake import IntakeAgent
from .records import RecordsAgent
from .refunds import RefundsAgent
from .reporting import ReportingAgent

AGENT_CLASSES = {cls.name: cls for cls in (IntakeAgent, EmailAgent, RecordsAgent, RefundsAgent, ReportingAgent)}

__all__ = ["AGENT_CLASSES", "BaseAgent", "EmailAgent", "IntakeAgent", "RecordsAgent",
           "RefundsAgent", "ReportingAgent", "StepResult"]
