from forkit.parser.ingredients import structure_ingredient


def test_real_parser_preserves_quantity_unit_and_name():
    ingredient = structure_ingredient('2 cups flour')
    assert ingredient['qty'] == '2'
    assert ingredient['unit'] == 'cup'
    assert ingredient['item'] == 'flour'
    assert ingredient['canonical_token'] == 'flour'


def test_fraction_and_cost_annotation_are_preserved():
    ingredient = structure_ingredient('1/2 cup corn kernels (frozen, $0.31)')
    assert ingredient['raw_text'] == '1/2 cup corn kernels (frozen, $0.31)'
    assert ingredient['qty'] == '1/2'
    assert ingredient['unit'] == 'cup'
    assert 'corn' in ingredient['item']
