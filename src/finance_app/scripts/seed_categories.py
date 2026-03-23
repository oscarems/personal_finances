#!/usr/bin/env python3
"""
Script seguro para agregar categorías predeterminadas a la base de datos.
Solo agrega categorías si no existen, sin afectar datos existentes.
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from finance_app.database import SessionLocal
from finance_app.models import CategoryGroup, Category
from finance_app.config import DEFAULT_CATEGORY_GROUPS


def seed_categories():
    """Agrega categorías predeterminadas si no existen"""
    db_session = SessionLocal()

    try:
        # Count existing categories
        existing_groups = db_session.query(CategoryGroup).count()
        existing_categories = db_session.query(Category).count()

        print("=" * 60)
        print("AGREGAR CATEGORÍAS PREDETERMINADAS")
        print("=" * 60)
        print(f"\nEstado actual:")
        print(f"  - Grupos de categorías: {existing_groups}")
        print(f"  - Categorías: {existing_categories}")

        if existing_categories > 0:
            print("\n⚠️  Ya existen categorías en la base de datos.")
            response = input("\n¿Deseas agregar las categorías predeterminadas de todos modos? (s/n): ")
            if response.lower() != 's':
                print("❌ Operación cancelada")
                return

        categories_added = 0
        groups_added = 0

        print("\n📦 Procesando grupos de categorías...")

        # Create expense category groups
        for idx, group_data in enumerate(DEFAULT_CATEGORY_GROUPS):
            group = db_session.query(CategoryGroup).filter_by(name=group_data['name']).first()
            if not group:
                group = CategoryGroup(
                    name=group_data['name'],
                    sort_order=idx,
                    is_income=False
                )
                db_session.add(group)
                db_session.flush()  # Get the ID
                print(f"  ✓ Grupo creado: {group_data['name']}")
                groups_added += 1
            else:
                print(f"  ⊙ Grupo existente: {group_data['name']}")

            # Create categories in this group
            for cat_idx, cat_data in enumerate(group_data['categories']):
                if isinstance(cat_data, str):
                    cat_name = cat_data
                    rollover_type = 'reset'
                else:
                    cat_name = cat_data['name']
                    rollover_type = cat_data.get('rollover_type', 'reset')

                category = db_session.query(Category).filter_by(
                    category_group_id=group.id,
                    name=cat_name
                ).first()

                if not category:
                    category = Category(
                        category_group_id=group.id,
                        name=cat_name,
                        sort_order=cat_idx,
                        rollover_type=rollover_type
                    )
                    db_session.add(category)
                    rollover_indicator = "🎯" if rollover_type == 'accumulate' else ""
                    print(f"    ✓ Categoría creada: {cat_name} {rollover_indicator}")
                    categories_added += 1

        # Create Income category group
        income_group = db_session.query(CategoryGroup).filter_by(name='Ingresos').first()
        if not income_group:
            income_group = CategoryGroup(
                name='Ingresos',
                sort_order=999,
                is_income=True
            )
            db_session.add(income_group)
            db_session.flush()
            print(f"  ✓ Grupo creado: Ingresos")
            groups_added += 1
        else:
            print(f"  ⊙ Grupo existente: Ingresos")

        # Income categories
        income_categories = ['Salario', 'Freelance', 'Inversiones', 'Otros']
        for cat_idx, cat_name in enumerate(income_categories):
            category = db_session.query(Category).filter_by(
                category_group_id=income_group.id,
                name=cat_name
            ).first()

            if not category:
                category = Category(
                    category_group_id=income_group.id,
                    name=cat_name,
                    sort_order=cat_idx
                )
                db_session.add(category)
                print(f"    ✓ Categoría creada: {cat_name}")
                categories_added += 1

        db_session.commit()

        print("\n" + "=" * 60)
        print("✅ COMPLETADO")
        print("=" * 60)
        print(f"\n📊 Resumen:")
        print(f"  - Grupos agregados: {groups_added}")
        print(f"  - Categorías agregadas: {categories_added}")

        if categories_added == 0 and groups_added == 0:
            print("\n💡 No se agregó nada porque todas las categorías ya existían.")
        else:
            print("\n✓ Las categorías predeterminadas están listas para usar.")

    except Exception as e:
        db_session.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db_session.close()


if __name__ == "__main__":
    seed_categories()
