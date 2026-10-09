# Mocking with pytest-mock

Every mock in a test comes from the `mocker` fixture (pytest-mock, a dev dependency). `mocker` undoes each patch at test end, so there are no context managers or decorators. Never import `unittest.mock` (`docs/adr/0007-pytest-everywhere.md`).

## Basic Mocking

**Isolate code from external dependencies:**
```python
import pytest
import requests

class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_user(self, user_id: int) -> dict:
        response = requests.get(f"{self.base_url}/users/{user_id}")
        response.raise_for_status()
        return response.json()

def test_get_user_success(mocker):
    """Test with mock response."""
    client = APIClient("https://api.example.com")

    mock_get = mocker.patch("requests.get")
    mock_get.return_value.json.return_value = {"id": 1, "name": "John"}
    mock_get.return_value.raise_for_status.return_value = None

    user = client.get_user(1)

    assert user["id"] == 1
    mock_get.assert_called_once_with("https://api.example.com/users/1")
```

## Mock Types

### Mock
**Basic mock object:**
```python
def test_mock(mocker):
    mock = mocker.Mock()
    mock.return_value = 42
    assert mock() == 42

    mock.method.return_value = "result"
    assert mock.method() == "result"
```

### MagicMock
**Mock with magic methods:**
```python
def test_magic_mock(mocker):
    mock = mocker.MagicMock()
    mock.__len__.return_value = 5
    assert len(mock) == 5

    mock.__getitem__.return_value = "item"
    assert mock[0] == "item"
```

## Patching

### Patch a function
```python
def test_function(mocker):
    mock_func = mocker.patch("module.function", return_value="mocked")
    assert module.function() == "mocked"
    mock_func.assert_called_once_with()
```

### Patch a method on a class
```python
def test_method(mocker):
    mocker.patch.object(MyClass, "method", return_value="mocked")
    assert MyClass().method() == "mocked"
```

### Spy: call through and record
```python
def test_spy(mocker):
    spy = mocker.spy(module, "function")
    module.function(1)
    spy.assert_called_once_with(1)
```

## Side Effects

**Simulate exceptions or sequences:**
```python
def test_side_effects(mocker):
    # Raise exception
    mock = mocker.Mock(side_effect=ValueError("Error message"))
    with pytest.raises(ValueError):
        mock()

    # Return sequence
    mock = mocker.Mock(side_effect=[1, 2, 3])
    assert [mock(), mock(), mock()] == [1, 2, 3]

    # Custom function
    mock = mocker.Mock(side_effect=lambda x: x * 2)
    assert mock(5) == 10
```

## Assertions

**Verify mock interactions:**
```python
def test_assertions(mocker):
    mock = mocker.Mock()
    mock(1, 2, key="value")

    assert mock.called
    assert mock.call_count == 1

    mock.assert_called_once()
    mock.assert_called_with(1, 2, key="value")
    mock.assert_called_once_with(1, 2, key="value")

    mock_other = mocker.Mock()
    mock_other.assert_not_called()
```

## Best Practices

1. **Mock at boundaries**: Mock external systems (APIs, databases, files)
2. **Don't over-mock**: Test real code when possible
3. **Verify interactions**: Use assertions to verify calls
4. **Clear return values**: Always define expected return values
5. **Reset between tests**: `mocker` undoes every patch at test end
6. **Mock the interface**: Mock at the lowest dependency level
7. **Use spec**: `mocker.Mock(spec=ClassName)` prevents invalid attribute access
