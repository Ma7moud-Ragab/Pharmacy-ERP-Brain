using PharmacyERP.Application.Common.DTOs;
using PharmacyERP.Application.Features.Identity.DTOs;

namespace PharmacyERP.Application.Features.Identity.Services.Interfaces;

public interface IBranchService
{
    Task<Result<PagedResult<BranchDto>>> GetPagedAsync(bool includeInactive, string? search, int page, int pageSize, CancellationToken ct = default);
    Task<Result<BranchDto>> GetByIdAsync(Guid branchId, CancellationToken ct = default);
    Task<Result<BranchDto>> CreateAsync(CreateBranchRequest request, CancellationToken ct = default);
    Task<Result<BranchDto>> UpdateAsync(Guid branchId, UpdateBranchRequest request, CancellationToken ct = default);
    Task<Result<EnrollmentTokenResponse>> IssueEnrollmentTokenAsync(Guid branchId, CancellationToken ct = default);
    Task<Result<RedeemBranchEnrollmentResponse>> RedeemEnrollmentAsync(RedeemBranchEnrollmentRequest request, CancellationToken ct = default);
}
