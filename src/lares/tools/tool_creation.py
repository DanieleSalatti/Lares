"""Tool creation utilities for self-extending capabilities."""

import ast

import structlog

from lares.tools.base import InvalidToolCodeError

log = structlog.get_logger()


def validate_tool_code(source_code: str) -> tuple[str, str]:
    """
    Validate Python source code for a tool function.

    The main tool function should be the last top-level function defined.
    Helper functions are allowed and encouraged for clean code.

    Returns (function_name, docstring) if valid.
    Raises InvalidToolCodeError if invalid.
    """
    # Parse the code
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        raise InvalidToolCodeError(f"Syntax error: {e}")

    # Find top-level function definitions (the last one is the main tool)
    top_level_functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
    ]

    if len(top_level_functions) == 0:
        raise InvalidToolCodeError("No function definition found")

    # The last top-level function is the main tool entry point
    main_func = top_level_functions[-1]
    func_name = main_func.name

    # Validate function name (no dangerous names)
    dangerous_names = ["exec", "eval", "compile", "__import__", "open", "system"]
    if func_name in dangerous_names:
        raise InvalidToolCodeError(f"Function name '{func_name}' is not allowed")

    # Main function must have a docstring
    docstring = ast.get_docstring(main_func)
    if not docstring:
        raise InvalidToolCodeError("Main function must have a docstring")

    # Check for dangerous AST nodes
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise InvalidToolCodeError(
                "Import statements are not allowed - tools run in Letta's sandbox"
            )

    log.info("tool_code_validated", function_name=func_name)
    return func_name, docstring
