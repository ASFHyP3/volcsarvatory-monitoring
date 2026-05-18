import pytest

import main


def test_product_id_from_message(sentinel1_burst_message):
    assert 'S1_247728_IW1_20251003T154900_VV_657C-BURST' == main.product_id_from_message(sentinel1_burst_message)
    with pytest.raises(ValueError):
        main.product_id_from_message({'granule_ur': 'S1_247728_IW1_20251003T154900_VH_657C-BURST'})
    with pytest.raises(ValueError):
        main.product_id_from_message({'granule_ur': 'S1X'})
    with pytest.raises(ValueError):
        main.product_id_from_message({'granule_ur': 'FOO'})
    with pytest.raises(ValueError):
        main.product_id_from_message({'granule_ur': 'S2X'})
