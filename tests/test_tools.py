"""Tests for tool validation."""

import pytest

from lares.tools import InvalidToolCodeError, validate_tool_code


def test_validate_tool_code_valid():
    """Test that valid code passes validation."""
    source = '''
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
'''
    func_name, docstring = validate_tool_code(source)
    assert func_name == "greet"
    assert "Greet someone" in docstring


def test_validate_tool_code_no_function():
    """Test that code without a function fails."""
    source = "x = 1 + 2"
    with pytest.raises(InvalidToolCodeError, match="No function definition found"):
        validate_tool_code(source)


def test_validate_tool_code_with_helpers():
    """Test that helper functions are allowed."""
    source = '''
def _helper(x: int) -> int:
    """Private helper."""
    return x * 2

def calculate(value: int) -> int:
    """Calculate something using a helper."""
    return _helper(value) + 1
'''
    func_name, docstring = validate_tool_code(source)
    # Last function is the main tool
    assert func_name == "calculate"
    assert "Calculate something" in docstring


def test_validate_tool_code_no_docstring():
    """Test that function without docstring fails."""
    source = '''
def greet(name: str) -> str:
    return f"Hello, {name}!"
'''
    with pytest.raises(InvalidToolCodeError, match="must have a docstring"):
        validate_tool_code(source)


def test_validate_tool_code_syntax_error():
    """Test that invalid syntax fails."""
    source = "def foo(:"
    with pytest.raises(InvalidToolCodeError, match="Syntax error"):
        validate_tool_code(source)


def test_validate_tool_code_dangerous_name():
    """Test that dangerous function names fail."""
    source = '''
def exec(code: str) -> str:
    """Execute code."""
    pass
'''
    with pytest.raises(InvalidToolCodeError, match="not allowed"):
        validate_tool_code(source)


def test_validate_tool_code_import_not_allowed():
    """Test that imports are not allowed."""
    source = '''
import os

def list_files(path: str) -> str:
    """List files in a directory."""
    return str(os.listdir(path))
'''
    with pytest.raises(InvalidToolCodeError, match="Import statements"):
        validate_tool_code(source)
