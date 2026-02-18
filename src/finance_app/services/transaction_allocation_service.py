from typing import Dict, List

from finance_app.models import Category, Transaction


def get_category_allocations(transaction: Transaction) -> List[Dict]:
    """Return category allocations for transaction using splits if present.

    Backward-compatible behavior:
    - If splits exist, use each split amount/category.
    - Otherwise use header category_id and full transaction amount.
    """
    allocations: List[Dict] = []
    if transaction.splits:
        for split in transaction.splits:
            allocations.append(
                {
                    "category_id": split.category_id,
                    "category_name": split.category.name if split.category else None,
                    "amount": split.amount,
                }
            )
        return allocations

    allocations.append(
        {
            "category_id": transaction.category_id,
            "category_name": transaction.category.name if transaction.category else None,
            "amount": transaction.amount,
        }
    )
    return allocations


def validate_splits_sum(total_amount: float, split_amounts: List[float]) -> bool:
    return round(sum(split_amounts), 2) == round(total_amount, 2)


def validate_splits_categories_exist(category_map: Dict[int, Category], split_category_ids: List[int]) -> bool:
    return all(category_id in category_map for category_id in split_category_ids)
