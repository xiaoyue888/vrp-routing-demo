from vrp_demo.scenarios import built_in_scenario, random_scenario


def test_built_in_scenario_is_stable():
    first = built_in_scenario()
    second = built_in_scenario()
    assert first == second
    assert len(first.customers) == 12


def test_random_scenario_is_reproducible():
    assert random_scenario(seed=42) == random_scenario(seed=42)
    assert random_scenario(seed=42) != random_scenario(seed=43)
