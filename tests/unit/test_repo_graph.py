"""P2 RAG unit tests — deterministic repository symbol graph."""

from agent.repo_graph import RepoGraph

FILES = {
    "com/specproof/demo/controller/UserController.java": """package com.specproof.demo.controller;

@RestController
public class UserController {

    @PutMapping("/{id}/email")
    @PreAuthorize("isAuthenticated()")
    public UserResponse changeEmail(Long id, ChangeEmailRequest request) {
        return userService.changeEmail(id, request);
    }

    @GetMapping("/{id}")
    public UserResponse getUser(Long id) {
        return userService.getUser(id);
    }
}
""",
    "com/specproof/demo/service/UserService.java": """package com.specproof.demo.service;

@Service
public class UserService {

    @Transactional
    public UserResponse changeEmail(Long userId, ChangeEmailRequest request) {
        userRepository.save(user);
        invalidateOldTokens(userId);
        rabbitTemplate.convertAndSend("specproof.demo.events", event);
        return new UserResponse(user.getId(), user.getUsername(), user.getEmail());
    }

    private void invalidateOldTokens(Long userId) {
        redisTemplate.delete("token:user:" + userId);
    }

    public UserResponse getUser(Long id) {
        return new UserResponse(id, "u", "e");
    }
}
""",
}


def test_graph_builds_methods():
    graph = RepoGraph(FILES)
    assert any(m.endswith(".changeEmail") for m in graph.methods)
    assert any(m.endswith(".invalidateOldTokens") for m in graph.methods)


def test_neighbors_include_callees():
    graph = RepoGraph(FILES)
    svc = next(m for m in graph.methods if m.endswith("UserService.changeEmail"))
    neighbors = graph.neighbors(svc, hops=1)
    # callee invalidateOldTokens + siblings (getUser)
    assert any(".invalidateOldTokens" in n for n in neighbors)
    assert any(n.endswith("UserService.getUser") for n in neighbors)


def test_neighbors_include_callers():
    graph = RepoGraph(FILES)
    svc = next(m for m in graph.methods if m.endswith("UserService.invalidateOldTokens"))
    neighbors = graph.neighbors(svc, hops=1)
    # caller changeEmail (service) is in the neighborhood
    assert any(n.endswith("UserService.changeEmail") for n in neighbors)


def test_expand_hits_returns_surrounding_context():
    graph = RepoGraph(FILES)
    hits = [{
        "path": "com/specproof/demo/service/UserService.java",
        "symbol": "changeEmail",
        "content": "...",
    }]
    expanded = graph.expand_hits(hits, hops=1)
    symbols = {h["symbol"] for h in expanded}
    assert "invalidateOldTokens" in symbols
    assert "getUser" in symbols


def test_unknown_symbol_returns_empty():
    graph = RepoGraph(FILES)
    assert graph.neighbors("com.unknown.Klass.nope", hops=1) == []
