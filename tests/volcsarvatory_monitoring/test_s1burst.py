from copy import deepcopy

import s1burst


def test_product_qualifies_sentinel1_processing(asf_product_factory) -> None:
    scene_name = 'S1_125344_IW1_20251003T154900_VV_657C-BURST'
    full_burst_id = '059_125344_IW1'
    polarization = 'VV'
    start_time = '2025-10-03T15:49:00+00:00'
    good_product = asf_product_factory(scene_name, full_burst_id, polarization, start_time)

    assert s1burst.product_qualifies_for_sentinel1_processing(good_product)

    product = deepcopy(good_product)
    product.properties['burst']['fullBurstID'] = 'foobar'
    assert not s1burst.product_qualifies_for_sentinel1_processing(product)

    product = deepcopy(good_product)
    product.properties['polarization'] = 'HH'
    assert s1burst.product_qualifies_for_sentinel1_processing(product)

    product = deepcopy(good_product)
    product.properties['polarization'] = 'HV'
    assert not s1burst.product_qualifies_for_sentinel1_processing(product)
