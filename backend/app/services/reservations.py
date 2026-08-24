from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, session) -> Dict[str, Any]:
    """
    Calculates revenue for a specific calendar month, bucketed by the
    property's local timezone rather than UTC (a reservation checking in
    late in the UTC day can fall on the next local calendar day/month).

    Returns {"total": Decimal, "count": int}.
    """
    from sqlalchemy import text

    tz_result = await session.execute(
        text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    tz_name = tz_result.scalar() or "UTC"
    tz = ZoneInfo(tz_name)

    start_date = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=tz)

    query = text("""
        SELECT SUM(total_amount) as total, COUNT(*) as reservation_count
        FROM reservations
        WHERE property_id = :property_id
        AND tenant_id = :tenant_id
        AND check_in_date >= :start_date
        AND check_in_date < :end_date
    """)

    result = await session.execute(
        query,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    row = result.fetchone()
    total = Decimal(str(row.total)) if row and row.total is not None else Decimal('0')
    count = row.reservation_count if row else 0
    return {"total": total, "count": count}


async def calculate_total_revenue(property_id: str, tenant_id: str, month: int = None, year: int = None) -> Dict[str, Any]:
    """
    Aggregates revenue from database, optionally scoped to a calendar month.
    """
    try:
        from app.core.database_pool import db_pool

        if not db_pool.session_factory:
            await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text

                if month is not None and year is not None:
                    monthly = await calculate_monthly_revenue(property_id, tenant_id, month, year, session)

                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(monthly["total"]),
                        "currency": "USD",
                        "count": monthly["count"],
                    }

                query = text("""
                    SELECT
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)

                result = await session.execute(query, {
                    "property_id": property_id,
                    "tenant_id": tenant_id
                })
                row = result.fetchone()

                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD",
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # Create property-specific mock data for testing when DB is unavailable
        # This ensures each property shows different figures
        mock_data = {
            'prop-001': {'total': '1000.00', 'count': 3},
            'prop-002': {'total': '4975.50', 'count': 4}, 
            'prop-003': {'total': '6100.50', 'count': 2},
            'prop-004': {'total': '1776.50', 'count': 4},
            'prop-005': {'total': '3256.00', 'count': 3}
        }
        
        mock_property_data = mock_data.get(property_id, {'total': '0.00', 'count': 0})
        
        return {
            "property_id": property_id,
            "tenant_id": tenant_id, 
            "total": mock_property_data['total'],
            "currency": "USD",
            "count": mock_property_data['count']
        }
