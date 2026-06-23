import inventory


def test_weighted_average_canonical_575():
    # 10 @ 5.00 then 10 @ 6.50 -> (50 + 65) / 20 = 5.75
    after_first = inventory.weighted_average(0, 0.0, 10, 5.00)
    assert after_first == 5.00
    after_second = inventory.weighted_average(10, 5.00, 10, 6.50)
    assert round(after_second, 4) == 5.75


def test_weighted_average_zero_on_hand_takes_receipt_cost():
    assert inventory.weighted_average(0, 9.99, 5, 2.00) == 2.00


def test_weighted_average_negative_on_hand_resets_to_receipt_cost():
    # Guard: never blend into a negative base.
    assert inventory.weighted_average(-3, 4.00, 5, 2.00) == 2.00


def test_weighted_average_zero_total_keeps_current_cost():
    assert inventory.weighted_average(0, 4.00, 0, 0.0) == 4.00
