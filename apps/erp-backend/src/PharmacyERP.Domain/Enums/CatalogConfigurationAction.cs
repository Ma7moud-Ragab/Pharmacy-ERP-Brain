namespace PharmacyERP.Domain.Enums;

/// <summary>
/// Actions tracked for catalog configuration audit logging.
/// </summary>
public enum CatalogConfigurationAction
{
    CreateProduct = 1,
    UpdateProduct = 2,
    AddUom = 3,
    UpdateUom = 4,
    DeactivateUom = 5
}
