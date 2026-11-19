-- One-time reconciliation. Execute explicitly with psql.
\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL SERIALIZABLE;
SET LOCAL lock_timeout = '5s';

WITH eligible AS MATERIALIZED (
    SELECT s.id, s.iso_reference,
           jsonb_build_object(
               'is_purchased', s.is_purchased, 'purchased_at', s.purchased_at,
               'purchased_by', s.purchased_by, 'purchase_notes', s.purchase_notes
           ) AS old_value
    FROM public.standards s
    WHERE NOT s.is_purchased
      AND EXISTS (
          SELECT FROM public.documents d
          WHERE d.standard_id = s.id AND d.is_current
      )
      -- Pre-publication stages have a numeric major below 60.
      AND CASE WHEN trim(split_part(s.stage_code, '.', 1)) ~ '^[+-]?[0-9]+$'
               THEN trim(split_part(s.stage_code, '.', 1))::numeric >= 60
               ELSE true END
    ORDER BY s.id
    FOR UPDATE OF s
), changed AS (
    UPDATE public.standards s
    SET is_purchased = true, purchased_at = transaction_timestamp(),
        purchased_by = NULL, updated_at = transaction_timestamp()
    FROM eligible e WHERE s.id = e.id
    RETURNING s.id, s.iso_reference, e.old_value,
              jsonb_build_object(
                  'is_purchased', s.is_purchased, 'purchased_at', s.purchased_at,
                  'purchased_by', s.purchased_by, 'purchase_notes', s.purchase_notes
              ) AS new_value
), history AS (
    INSERT INTO public.standard_history
        (standard_id, event_type, source, old_value, new_value, notes)
    SELECT id, 'purchased', 'system', old_value, new_value,
           'One-time purchase backfill for an existing uploaded document'
    FROM changed RETURNING standard_id
), audit AS (
    INSERT INTO public.audit_logs (action, resource_type, resource_id, payload)
    SELECT 'standard.purchased', 'standard', id,
           jsonb_build_object('iso_reference', iso_reference,
                              'reason', 'existing_document_backfill')
    FROM changed RETURNING resource_id
)
SELECT c.iso_reference AS marked_purchased
FROM changed c JOIN history h ON h.standard_id = c.id
JOIN audit a ON a.resource_id = c.id ORDER BY c.iso_reference;
COMMIT;
