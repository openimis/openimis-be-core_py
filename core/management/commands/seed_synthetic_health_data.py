"""
DISCLAIMER:

This generates SYNTHETIC TEST DATA ONLY
All data (names, addresses, IDs, claims) is randomly generated
It does NOT represent real individuals or actual medical cases
Intended for development, testing, and performance evaluation
Should NOT be used in production with real patient data
Django Management Command for Bulk Synthetic Data Generation


TODO: to generate this data more realistic and diversion, based on HF, location, Claim, Family that looks more realistic approach
Usage:
    # Generate 1000 families with 4 members each, and 2 claims per insuree
    python manage.py generate_synthetic_data --families 1000 --members 4 --claims 2

    # Generate 50,000 families with 5 members each, no claims
    python manage.py generate_synthetic_data --families 50000 --members 5

    # Use a preset for medium size data generation and skip the confirmation prompt
    python manage.py generate_synthetic_data --preset medium --claims 1 --no-confirm
"""

import gc
import random
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from faker import Faker
# Local app imports
from claim.models import Claim, ClaimItem, ClaimService
from core.models import Officer
from insuree.models import (ConfirmationType, Education, Family, FamilyType,
                            Gender, IdentificationType, Insuree, InsureePolicy,
                            Profession, Relation, InsureeStatus)
from location.models import HealthFacility, Location
from medical.models import Diagnosis, Item, Service
from policy.models import Policy
from product.models import Product


class PostgreSQLOptimizer: #for quick generation , this is only for developement and testing do not use in production!!
    """PostgreSQL-specific optimizations for bulk operations"""
    @staticmethod
    def optimize_for_bulk_insert():
        with connection.cursor() as cursor:
            cursor.execute("SET work_mem = '256MB'")
            cursor.execute("SET maintenance_work_mem = '512MB'")
            cursor.execute("SET synchronous_commit = OFF")

    @staticmethod
    def reset_optimizations():
        with connection.cursor() as cursor:
            cursor.execute("RESET work_mem")
            cursor.execute("RESET maintenance_work_mem")
            cursor.execute("SET synchronous_commit = ON")


class DataGenerator:
    """Generate realistic test data using Faker library"""
    
    def __init__(self):
        self.faker = Faker()
        self.chf_id_counter = random.randint(100000000, 200000000)
    
    def get_first_name(self):
        return self.faker.first_name()
    
    def get_last_name(self):
        return self.faker.last_name()
    
    def get_address(self):
        return self.faker.street_address() + ", " + self.faker.city()
    
    def get_unique_chf_id(self):
        self.chf_id_counter += 1
        return f"CHF{self.chf_id_counter:09d}"


class BulkInsureeGenerator:
    def __init__(self, batch_size=2000, stdout=None):
        self.batch_size = batch_size
        self.data_gen = DataGenerator()
        self.stdout = stdout

    def write(self, message):
        if self.stdout: self.stdout.write(message)
        else: print(message)

    def setup_reference_data(self, generate_claims=False):
        """Cache reference data to avoid repeated DB queries"""
        self.write("Loading and setting up reference data...")
        self.genders = list(Gender.objects.all()) or list(Gender.objects.bulk_create([Gender(code='M'), Gender(code='F')]))
        self.family_types = list(FamilyType.objects.all()) or list(FamilyType.objects.bulk_create([FamilyType(code='N', type='Nuclear')]))
        # TODO: Filter out inactive locations - currently including all which might cause issues
        self.locations = list(Location.objects.all()[:200])
        self.health_facilities = list(HealthFacility.objects.all()[:100])
        self.products = list(Product.objects.all()[:20])
        # TODO: Should we filter officers by district/region? Currently random assignment
        self.officers = list(Officer.objects.all()[:50])

        required_data = {
            "locations": self.locations, "health facilities": self.health_facilities,
            "products": self.products, "officers": self.officers
        }
        for name, data_list in required_data.items():
            if not data_list: raise CommandError(f"No data found for {name}. Please populate reference data.")

        if generate_claims:
            self.diagnoses = list(Diagnosis.objects.all()[:500])
            self.items = list(Item.objects.all()[:1000])
            self.services = list(Service.objects.all()[:500])
            required_claim_data = { "diagnoses": self.diagnoses, "medical items": self.items, "medical services": self.services }
            for name, data_list in required_claim_data.items():
                if not data_list: raise CommandError(f"To generate claims, please populate reference data for {name}.")
        self.write("Reference data loaded.")

    def _bulk_create_with_progress(self, model_class, objects, description):
        total = len(objects)
        if total == 0: return []
        self.write(f"Creating {total:,} {description}...")
        created_objects = []
        for i in range(0, total, self.batch_size):
            batch = objects[i:i + self.batch_size]
            with transaction.atomic():
                created_batch = model_class.objects.bulk_create(batch, batch_size=self.batch_size)
                created_objects.extend(created_batch)
            progress = (len(created_objects) / total) * 100
            self.write(f"  Progress: {len(created_objects):,}/{total:,} ({progress:.1f}%) {description}")
            gc.collect()
        return created_objects

    def _generate_insurees(self, total_insuree_count):
        self.write(f"\n=== Generating {total_insuree_count:,} Insurees (unassigned) ===")
        insurees_to_create = []
        for _ in range(total_insuree_count):
            insuree = Insuree(
                uuid=str(uuid.uuid4()), chf_id=self.data_gen.get_unique_chf_id(),
                last_name=self.data_gen.get_last_name(), other_names=self.data_gen.get_first_name(),
                gender=random.choice(self.genders), dob=date.today() - timedelta(days=random.randint(1, 30000)),
                head=False, card_issued=random.choice([True, False]), audit_user_id=1, validity_from=timezone.now(), status=InsureeStatus.ACTIVE,
                health_facility=random.choice(self.health_facilities) if self.health_facilities else None,
            )
            insurees_to_create.append(insuree)
        return self._bulk_create_with_progress(Insuree, insurees_to_create, "insurees")

    def _generate_families_and_link_members(self, all_insurees, num_families, num_members):
        self.write(f"\n=== Generating {num_families:,} Families and linking {num_members} members to each ===")
        if len(all_insurees) < num_families * num_members:
            raise CommandError("Not enough insurees to form the requested families.")
        
        insurees_pool = list(all_insurees)
        random.shuffle(insurees_pool)
        
        heads_pool, members_pool = insurees_pool[:num_families], insurees_pool[num_families:]
        families_to_create = [Family(uuid=str(uuid.uuid4()), head_insuree=h, location=random.choice(self.locations),
                                     family_type=random.choice(self.family_types), address=self.data_gen.get_address(),
                                     audit_user_id=1, validity_from=timezone.now()) for h in heads_pool]
        created_families = self._bulk_create_with_progress(Family, families_to_create, "families")
        
        self.write("Linking family members...")
        insurees_to_update = []
        for family in created_families:
            head = family.head_insuree
            head.family, head.head = family, True
            insurees_to_update.append(head)
            for _ in range(num_members - 1):
                if not members_pool: break
                member = members_pool.pop()
                member.family = family
                insurees_to_update.append(member)
        
        self.write(f"Bulk updating {len(insurees_to_update):,} insurees with family links...")
        Insuree.objects.bulk_update(insurees_to_update, ['family', 'head'], batch_size=self.batch_size)
        return created_families

    def _generate_policies(self, families):
        self.write(f"\n=== Generating policies for {len(families):,} families ===")
        policies_to_create = []
        for f in families:
            enroll_date = date.today() - timedelta(days=random.randint(90, 730))
            # TODO: Add support for different policy stages (not just 'N')
            policy = Policy(
                uuid=str(uuid.uuid4()), stage='N', status=Policy.STATUS_ACTIVE, value=random.uniform(100.0, 2000.0),
                family=f, enroll_date=enroll_date, start_date=enroll_date, effective_date=enroll_date,
                expiry_date=enroll_date + timedelta(days=365), product=random.choice(self.products),
                officer=random.choice(self.officers), audit_user_id=1
            )
            policies_to_create.append(policy)
        return self._bulk_create_with_progress(Policy, policies_to_create, "policies")


    def _generate_insuree_policies(self, policies):
        self.write(f"\n=== Generating InsureePolicy relationships ===")
        family_ids = [p.family_id for p in policies]
        insurees = Insuree.objects.filter(family_id__in=family_ids)
        insurees_by_family = {fid: [] for fid in family_ids}
        for insuree in insurees: insurees_by_family[insuree.family_id].append(insuree)
        
        insuree_policies = [InsureePolicy(
                insuree=insuree, policy=p, enrollment_date=p.enroll_date, start_date=p.start_date,
                effective_date=p.effective_date, expiry_date=p.expiry_date, audit_user_id=1
            ) for p in policies for insuree in insurees_by_family.get(p.family_id, [])]
        self._bulk_create_with_progress(InsureePolicy, insuree_policies, "InsureePolicy relationships")
        return len(insuree_policies)

    def _generate_claims(self, all_insurees, num_claims_per_insuree):
        self.write(f"\n=== Generating {num_claims_per_insuree} claims for each of {len(all_insurees):,} insurees ===")
        claims_to_create = []
        for insuree in all_insurees:
            for _ in range(num_claims_per_insuree):
                claim_date = date.today() - timedelta(days=random.randint(1, 80))
                # Note: Setting status to ENTERED - claims admin will need to review, Also TODO: we need to find data diversity of claims
                claim = Claim(
                    uuid=str(uuid.uuid4()), insuree=insuree, code=f"BULK-{uuid.uuid4()}",
                    date_from=claim_date, date_claimed=claim_date, status=Claim.STATUS_ENTERED,
                    health_facility=insuree.health_facility or random.choice(self.health_facilities),
                    icd=random.choice(self.diagnoses), audit_user_id=1, claimed=0
                )
                claims_to_create.append(claim)

        created_claims = self._bulk_create_with_progress(Claim, claims_to_create, "claims")
        
        claim_items_to_create, claim_services_to_create = [], []
        claim_totals = {c.id: Decimal(0) for c in created_claims}

        for claim in created_claims:
            # TODO: Make items/services count configurable instead of random, make it more realistic in TODO:
            for _ in range(random.randint(1, 4)): # 1-4 items per claim
                price = Decimal(random.uniform(5.0, 150.0)).quantize(Decimal("0.01"))
                qty = Decimal(random.randint(1, 5))
                claim_items_to_create.append(ClaimItem(
                    claim=claim, item=random.choice(self.items), status=1, qty_provided=qty,
                    price_asked=price, audit_user_id=1, availability=True
                ))
                claim_totals[claim.id] += price * qty
            
            for _ in range(random.randint(1, 3)): # 1-3 services per claim
                price = Decimal(random.uniform(50.0, 500.0)).quantize(Decimal("0.01"))
                qty = 1
                claim_services_to_create.append(ClaimService(
                    claim=claim, service=random.choice(self.services), status=1, qty_provided=qty,
                    price_asked=price, audit_user_id=1
                ))
                claim_totals[claim.id] += price * qty
        
        self._bulk_create_with_progress(ClaimItem, claim_items_to_create, "claim items")
        self._bulk_create_with_progress(ClaimService, claim_services_to_create, "claim services")

        self.write(f"Bulk updating {len(created_claims):,} claims with calculated totals...")
        for claim in created_claims: claim.claimed = claim_totals[claim.id]
        Claim.objects.bulk_update(created_claims, ['claimed'], batch_size=self.batch_size)
        
        return len(created_claims), len(claim_items_to_create), len(claim_services_to_create)

    def generate_bulk_data(self, num_families, num_members, num_claims):
        start_time = time.time()
        self.setup_reference_data(generate_claims=num_claims > 0)

        self.write("=" * 80 + f"\nBULK DATA GENERATION STARTED\nFamilies: {num_families:,}, Members/Family: {num_members}, Claims/Insuree: {num_claims}\n" + "=" * 80)
        PostgreSQLOptimizer.optimize_for_bulk_insert()
        
        results = {}
        try:
            total_insuree_count = num_families * num_members
            all_insurees = self._generate_insurees(total_insuree_count)
            families = self._generate_families_and_link_members(all_insurees, num_families, num_members)
            policies = self._generate_policies(families)
            insuree_policies = self._generate_insuree_policies(policies)

            results = {'families': len(families), 'insurees': len(all_insurees),
                       'policies': len(policies), 'insuree_policies': insuree_policies}

            if num_claims > 0:
                claims, items, services = self._generate_claims(all_insurees, num_claims)
                results.update({'claims': claims, 'claim_items': items, 'claim_services': services})

        finally:
            PostgreSQLOptimizer.reset_optimizations()
            self.write("\nDatabase optimizations have been reset.")

        duration = time.time() - start_time
        results['duration'] = duration
        
        self.write("\n" + "=" * 80 + "\nBULK SYNTHETIC DATA GENERATION COMPLETED SUCCESSFULLY!\n" + "=" * 80)
        for key, value in results.items():
            self.write(f"{key.replace('_', ' ').title():<25} {value:>12,.2f}" if isinstance(value, float) else f"{key.replace('_', ' ').title():<25} {value:>12,}")
        return results


class Command(BaseCommand):
    help = 'Generate bulk insuree, policy, and claim test data for the project.'

    def add_arguments(self, parser):
        parser.add_argument('--preset', choices=['small', 'medium', 'large'], help='Use preset configuration.')
        parser.add_argument('--families', type=int, default=1000, help='Number of families to generate.')
        parser.add_argument('--members', type=int, default=4, help='Fixed number of members per family.')
        parser.add_argument('--claims', type=int, default=0, help='Number of claims to generate per insuree. If 0, no claims are created.')
        parser.add_argument('--batch-size', type=int, default=2000, help='Batch size for bulk operations.')
        parser.add_argument('--no-confirm', action='store_true', help='Skip confirmation prompt.')

    def handle(self, *args, **options):
        presets = {
            'small': {'families': 1000, 'members': 3, 'claims': 1},
            'medium': {'families': 10000, 'members': 4, 'claims': 2},
            'large': {'families': 50000, 'members': 5, 'claims': 2}
        }
        
        config = {'families': options['families'], 'members': options['members'], 'claims': options['claims']}
        if options['preset']:
            config = presets[options['preset']]
            self.stdout.write(self.style.SUCCESS(f"Using preset '{options['preset']}' configuration"))

        if config['members'] < 1: raise CommandError("Number of members must be at least 1.")
        
        batch_size = options['batch_size']
        if config['families'] > 10000 and batch_size < 4000:
            batch_size = 5000
            self.stdout.write(self.style.WARNING(f"Auto-adjusted batch size to {batch_size} for large dataset"))

        total_insurees = config['families'] * config['members']
        total_claims = total_insurees * config['claims']

        self.stdout.write("\n" + "="*60 + "\n" + self.style.SUCCESS("DJANGO BULK SYNTHETIC DATA GENERATOR - OPENIMIS") + "\n" + "="*60)
        self.stdout.write(f"Families to create: {config['families']:,}\nMembers per family: {config['members']}\nTotal insurees: {total_insurees:,}")
        if config['claims'] > 0: self.stdout.write(f"Claims per insuree: {config['claims']}\nTotal claims: {total_claims:,}")
        
        
        if not options['no_confirm']:
            if input(f"\n{self.style.WARNING('WARNING:')} This will create a large amount of test data. Continue? (yes/no): ").lower() not in ['yes', 'y']:
                self.stdout.write(self.style.ERROR("Operation cancelled.")); return
        
        with transaction.atomic():
            generator = BulkInsureeGenerator(batch_size=batch_size, stdout=self.stdout)
            results = generator.generate_bulk_data(config['families'], config['members'], config['claims'])
        
        self.stdout.write(self.style.SUCCESS(f"\n Successfully generated synthetic data in {results['duration']:.2f} seconds!"))
