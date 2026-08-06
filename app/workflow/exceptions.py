class WorkflowError(Exception):
    """Base exception for workflow module."""


class WorkflowNotFoundError(WorkflowError):
    """Raised when workflow resource cannot be found."""


class WorkflowValidationError(WorkflowError):
    """Raised when workflow operation cannot be completed."""


class WorkflowPermissionError(WorkflowError):
    """Raised when user cannot perform transition."""
