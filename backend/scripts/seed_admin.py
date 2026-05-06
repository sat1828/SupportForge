#!/usr/bin/env python3
"""
Seed admin user and sample tickets for demo purposes.
Run: python scripts/seed_admin.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://supportforge:supportforge_dev@localhost:5432/supportforge")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "seed_script_secret_key_min_32_chars")
os.environ.setdefault("ENVIRONMENT", "development")

SAMPLE_TICKETS = [
    ("Order not delivered after 7 days", "I placed order #ORD-2024-7892 on April 14th. It's been 7 days and I have not received any tracking update. Please help.", "P2", "open"),
    ("GST Invoice needed urgently", "I need GST invoice for my recent purchase of ₹12,499. My GSTIN is 29ABCDE1234F1Z5. Please send it to my email.", "P3", "open"),
    ("Refund not received after 15 days", "I returned the product on April 10th. The pickup was done but refund of ₹3,200 has not been credited to my account.", "P2", "escalated"),
    ("COD order cancelled without notice", "My COD order worth ₹8,500 was cancelled automatically without my consent. I want to know why.", "P3", "open"),
    ("Wrong product delivered", "I ordered a blue shirt size L but received a red shirt size M. I need an exchange or full refund.", "P2", "open"),
    ("Duplicate payment charged", "Payment was deducted twice for order #ORD-2024-9123. Total extra deduction: ₹2,499. Please refund immediately.", "P1", "escalated"),
    ("Delivery agent rude behavior", "The delivery agent was extremely rude and refused to deliver to my floor. Please take action.", "P4", "resolved"),
    ("Product damaged in transit", "The laptop I ordered arrived with a cracked screen. I have photos as proof. Need replacement.", "P1", "open"),
    ("Unable to download invoice", "The invoice download button shows error 500. I need this for my company accounts by end of day.", "P3", "open"),
    ("Track my order ORD-2024-5678", "Please share tracking details for my order. The estimated delivery was yesterday.", "P3", "resolved"),
]


async def seed():
    from app.database import create_all_tables, AsyncSessionLocal
    from app.models.user import User, UserRole
    from app.models.ticket import Ticket, TicketStatus, TicketPriority, SLA_HOURS
    from app.core.security import hash_password

    await create_all_tables()

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)

        # Create admin user
        admin = User(
            id=uuid.uuid4(),
            email="admin@supportforge.dev",
            full_name="SupportForge Admin",
            hashed_password=hash_password("admin123"),
            role=UserRole.ADMIN,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(admin)

        # Create demo customer
        customer = User(
            id=uuid.uuid4(),
            email="customer@demo.com",
            full_name="Demo Customer",
            hashed_password=hash_password("customer123"),
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(customer)
        await db.flush()

        # Create sample tickets
        for i, (title, desc, priority, status) in enumerate(SAMPLE_TICKETS):
            p = TicketPriority(priority)
            sla_hours = SLA_HOURS.get(p, 24)
            created = now - timedelta(hours=i * 6)

            ticket = Ticket(
                id=uuid.uuid4(),
                customer_id=customer.id,
                title=title,
                description=desc,
                status=TicketStatus(status),
                priority=p,
                sla_deadline=created + timedelta(hours=sla_hours),
                resolved_at=created + timedelta(hours=2) if status == "resolved" else None,
                confidence_score=0.85 if status == "resolved" else None,
                llm_calls_made=2 if status != "open" else 0,
                tokens_consumed=850 if status != "open" else 0,
                created_at=created,
                updated_at=created,
            )
            db.add(ticket)

        await db.commit()
        print("✅ Admin and demo data seeded!")
        print("\nLogin credentials:")
        print("  Admin:    admin@supportforge.dev / admin123")
        print("  Customer: customer@demo.com / customer123")


if __name__ == "__main__":
    asyncio.run(seed())
