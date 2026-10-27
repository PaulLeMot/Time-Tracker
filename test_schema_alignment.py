import unittest

from sqlalchemy import Enum as SAEnum, String

from models import (
    Deal,
    DealProductType,
    Product,
    ProductType,
    Task,
    TaskExecution,
    TaskExecutionStatus,
    TechCardTask,
)
from schemas import DealProductCreate, DealProductItem


class SchemaAlignmentTests(unittest.TestCase):
    def test_deal_product_nullable_quantity_and_required_keys(self):
        table = DealProductType.__table__
        self.assertFalse(table.c.deal_id.nullable)
        self.assertFalse(table.c.product_id.nullable)
        self.assertTrue(table.c.quantity.nullable)

    def test_deal_product_unique_constraint_and_index(self):
        table = DealProductType.__table__
        unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("deal_id", "product_id"), unique_columns)
        self.assertIn("idx_deal_products_deal_id", {index.name for index in table.indexes})

    def test_nullable_quantity_pydantic_schemas(self):
        self.assertIsNone(DealProductItem(name="Design").quantity)
        self.assertIsNone(DealProductCreate(product_id=1).quantity)
        self.assertIsNone(DealProductItem(name="Design").model_dump()["quantity"])
        self.assertEqual(DealProductItem(name="Print", quantity=0).quantity, 0)

    def test_product_and_tech_card_nullability(self):
        self.assertFalse(Product.__table__.c.code.nullable)
        self.assertFalse(Product.__table__.c.product_type.nullable)
        self.assertTrue(TechCardTask.__table__.c.tech_card_id.nullable)
        self.assertIs(type(ProductType.__table__.c.full_name.type), String)

    def test_task_execution_uses_native_postgresql_enum(self):
        enum_type = TaskExecution.__table__.c.status.type
        self.assertIsInstance(enum_type, SAEnum)
        self.assertTrue(enum_type.native_enum)
        self.assertEqual(
            enum_type.enums,
            [status.value for status in TaskExecutionStatus],
        )

    def test_metadata_omits_unapproved_indexes_and_set_null_actions(self):
        self.assertNotIn("idx_tasks_type_id", {index.name for index in Task.__table__.indexes})
        execution_indexes = {index.name for index in TaskExecution.__table__.indexes}
        self.assertNotIn("idx_task_executions_employee_id", execution_indexes)
        self.assertNotIn("idx_task_executions_notification_id", execution_indexes)
        for column_name in ("ip_id", "mp_id"):
            foreign_key = next(iter(Deal.__table__.c[column_name].foreign_keys))
            self.assertIsNone(foreign_key.ondelete)


if __name__ == "__main__":
    unittest.main()
