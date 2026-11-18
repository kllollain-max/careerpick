"""Single-writer cutover readiness. Read-only: cannot switch publisher or POST."""
def evaluate(*, verified_post, receipt, backup, old_disabled, v4_enabled, queue_ready, image_reviewed):
    checks={"verified_post":bool(verified_post),
            "meta_receipt_id_and_permalink":bool(receipt and receipt.get("id") and receipt.get("permalink")),
            "backup_restorable":bool(backup),
            "old_publisher_disabled":bool(old_disabled),
            "v4_publisher_enabled":bool(v4_enabled),
            "queue_ready":bool(queue_ready),
            "image_reviewed":bool(image_reviewed)}
    if old_disabled and v4_enabled and not checks["verified_post"]:
        return {"status":"UNSAFE_CUTOVER","checks":checks,"cutover_allowed":False}
    return {"status":"READY" if all(checks.values()) else "NOT_READY",
            "checks":checks,"cutover_allowed":all(checks.values())}
