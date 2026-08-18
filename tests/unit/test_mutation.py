"""P4 unit tests — source-level mutation testing."""

from experiments.mutation import (
    generate_mutants,
    run_mutation_campaign,
)

SOURCE = """@Service
public class UserService {
    @Transactional
    public boolean canChange(Long userId) {
        if (userRepository.existsByEmail(email)) {
            return true;
        }
        if (userId == null) {
            return false;
        }
        return userRepository.save(user) != null;
    }
}
"""


def test_generate_mutants_covers_operators():
    mutants = generate_mutants(SOURCE)
    ops = {m.operator for m in mutants}
    assert "remove_annotation" in ops
    assert "flip_boolean" in ops
    assert "remove_null_check" in ops
    # return_flip needs literal true/false returns
    assert "return_flip" in ops


def test_annotation_mutant_drops_the_annotation():
    mutants = generate_mutants(SOURCE)
    ann = next(m for m in mutants if m.operator == "remove_annotation")
    assert "@Transactional" not in ann.content


def test_boolean_mutant_flips_comparison():
    mutants = generate_mutants(SOURCE)
    flipped = [m for m in mutants if m.operator == "flip_boolean"]
    assert flipped
    joined = "\n".join(m.content for m in flipped)
    assert "== null" in joined  # some mutant flipped != -> ==


def test_campaign_classifies_killed_and_survived():
    def test_runner(content: str) -> tuple[int, str]:
        # Kill any mutant that removes the annotation; others survive.
        if "@Transactional" not in content:
            return 1, ""
        return 0, ""

    report = run_mutation_campaign("UserService.java", SOURCE, test_runner)
    assert report.mutants_total >= 1
    assert report.killed >= 1  # annotation removal killed
    assert report.survived >= 1
    assert report.to_dict()["mutation_score"] == round(
        report.killed / report.mutants_total, 3
    )


def test_campaign_caps_mutants():
    mutants = generate_mutants(SOURCE, max_mutants=3)
    assert len(mutants) == 3
