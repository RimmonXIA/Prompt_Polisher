from fastapi.testclient import TestClient

from prompt_polisher.a2a_server import app, tasks

client = TestClient(app)

def test_get_agent_card():
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Prompt Polisher"
    assert data["capabilities"]["streaming"] is True

def test_handle_rpc_method_not_found():
    response = client.post("/a2a/v1", json={"jsonrpc": "2.0", "method": "NonExistent", "id": 1})
    assert response.status_code == 405
    assert response.json()["error"]["code"] == -32601

def test_handle_rpc_parse_error():
    response = client.post("/a2a/v1", content="invalid json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32700

def test_list_tasks_empty():
    tasks.clear()
    response = client.post("/a2a/v1", json={"jsonrpc": "2.0", "method": "ListTasks", "id": 2})
    assert response.status_code == 200
    assert response.json()["result"]["tasks"] == []

def test_send_message_missing_input():
    payload = {"jsonrpc": "2.0", "method": "SendMessage", "id": 3, "params": {}}
    response = client.post("/a2a/v1", json=payload)
    assert response.status_code == 200
    assert "error" in response.json()
    assert response.json()["error"]["code"] == -32602

def test_get_task_not_found():
    payload = {
        "jsonrpc": "2.0", "method": "GetTask", "id": 4, "params": {"id": "unknown"}
    }
    response = client.post("/a2a/v1", json=payload)
    assert response.status_code == 200
    assert "error" in response.json()
    assert response.json()["error"]["code"] == -32001

def test_send_message_success_mock(monkeypatch):
    # Mock background task execution
    monkeypatch.setattr("prompt_polisher.a2a_server.execute_task", lambda tid, inp: None)
    
    response = client.post("/a2a/v1", json={
        "jsonrpc": "2.0", 
        "method": "SendMessage", 
        "id": 5, 
        "params": {"input": "test prompt"}
    })
    assert response.status_code == 200
    res = response.json()["result"]
    task_id = res["task"]["id"]
    assert task_id in tasks
    assert tasks[task_id]["input"] == "test prompt"
