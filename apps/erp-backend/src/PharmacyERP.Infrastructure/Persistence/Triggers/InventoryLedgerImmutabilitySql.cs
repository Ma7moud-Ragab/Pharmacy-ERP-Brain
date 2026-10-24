namespace PharmacyERP.Infrastructure.Persistence.Triggers;

public static class InventoryLedgerImmutabilitySql
{
    public const string CreateFunctionAndTriggerSql = @"
CREATE OR REPLACE FUNCTION inventory.fn_prevent_posted_inventory_txn_mutation()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'DELETE') THEN
        IF OLD.status = 'POSTED' THEN
            RAISE EXCEPTION 'Cannot delete a POSTED inventory transaction.';
        END IF;
    ELSIF (TG_OP = 'UPDATE') THEN
        IF OLD.status = 'POSTED' THEN
            RAISE EXCEPTION 'Cannot update a POSTED inventory transaction.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION inventory.fn_prevent_posted_inventory_txn_line_mutation()
RETURNS TRIGGER AS $$
DECLARE
    parent_status VARCHAR(20);
BEGIN
    IF (TG_OP = 'DELETE') THEN
        SELECT status INTO parent_status 
        FROM inventory.""INVENTORY_TXN"" 
        WHERE inventory_txn_id = OLD.inventory_txn_id;

        IF parent_status = 'POSTED' THEN
            RAISE EXCEPTION 'Cannot delete lines from a POSTED inventory transaction.';
        END IF;
    ELSIF (TG_OP = 'UPDATE') THEN
        SELECT status INTO parent_status 
        FROM inventory.""INVENTORY_TXN"" 
        WHERE inventory_txn_id = OLD.inventory_txn_id;

        IF parent_status = 'POSTED' THEN
            RAISE EXCEPTION 'Cannot update lines of a POSTED inventory transaction.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_posted_inventory_txn_mutation ON inventory.""INVENTORY_TXN"";
CREATE TRIGGER trg_prevent_posted_inventory_txn_mutation
BEFORE UPDATE OR DELETE ON inventory.""INVENTORY_TXN""
FOR EACH ROW EXECUTE FUNCTION inventory.fn_prevent_posted_inventory_txn_mutation();

DROP TRIGGER IF EXISTS trg_prevent_posted_inventory_txn_line_mutation ON inventory.""INVENTORY_TXN_LINE"";
CREATE TRIGGER trg_prevent_posted_inventory_txn_line_mutation
BEFORE UPDATE OR DELETE ON inventory.""INVENTORY_TXN_LINE""
FOR EACH ROW EXECUTE FUNCTION inventory.fn_prevent_posted_inventory_txn_line_mutation();
";
}