-- Test to ensure financial aid doesn't exceed reasonable limits
select *
from {{ ref('stg_financial_aid') }}
where amount > 50000  -- Unreasonably high aid amount
   or amount < 0      -- Negative aid amount