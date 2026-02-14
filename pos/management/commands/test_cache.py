"""
Management command to test cache functionality
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from pos.cache_utils import get_cache_key
import time


class Command(BaseCommand):
    help = 'Test cache functionality (Redis or fallback)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Testing cache functionality...'))
        
        # Test 1: Basic set/get
        self.stdout.write('\n1. Testing basic cache operations:')
        test_key = 'test_key'
        test_value = {'message': 'Hello from cache!', 'timestamp': time.time()}
        
        cache.set(test_key, test_value, 60)
        retrieved = cache.get(test_key)
        
        if retrieved == test_value:
            self.stdout.write(self.style.SUCCESS('   ✓ Cache set/get working'))
        else:
            self.stdout.write(self.style.ERROR('   ✗ Cache set/get failed'))
            return
        
        # Test 2: Cache key generation
        self.stdout.write('\n2. Testing cache key generation:')
        key1 = get_cache_key('dashboard', 1, '2024-01-01')
        key2 = get_cache_key('dashboard', 1, '2024-01-01')
        key3 = get_cache_key('dashboard', 2, '2024-01-01')
        
        if key1 == key2:
            self.stdout.write(self.style.SUCCESS('   ✓ Consistent key generation'))
        else:
            self.stdout.write(self.style.ERROR('   ✗ Inconsistent key generation'))
        
        if key1 != key3:
            self.stdout.write(self.style.SUCCESS('   ✓ Unique keys for different params'))
        else:
            self.stdout.write(self.style.ERROR('   ✗ Keys not unique'))
        
        # Test 3: Cache expiration
        self.stdout.write('\n3. Testing cache expiration:')
        cache.set('expire_test', 'value', 1)  # 1 second TTL
        
        if cache.get('expire_test') == 'value':
            self.stdout.write(self.style.SUCCESS('   ✓ Value cached'))
        
        self.stdout.write('   Waiting 2 seconds...')
        time.sleep(2)
        
        if cache.get('expire_test') is None:
            self.stdout.write(self.style.SUCCESS('   ✓ Cache expiration working'))
        else:
            self.stdout.write(self.style.WARNING('   ⚠ Cache expiration may not be working'))
        
        # Test 4: Cache deletion
        self.stdout.write('\n4. Testing cache deletion:')
        cache.set('delete_test', 'value', 60)
        cache.delete('delete_test')
        
        if cache.get('delete_test') is None:
            self.stdout.write(self.style.SUCCESS('   ✓ Cache deletion working'))
        else:
            self.stdout.write(self.style.ERROR('   ✗ Cache deletion failed'))
        
        # Test 5: Check backend type
        self.stdout.write('\n5. Cache backend information:')
        from django.conf import settings
        cache_backend = settings.CACHES['default']['BACKEND']
        
        if 'redis' in cache_backend.lower():
            self.stdout.write(self.style.SUCCESS(f'   ✓ Using Redis: {cache_backend}'))
        else:
            self.stdout.write(self.style.WARNING(f'   ⚠ Using fallback: {cache_backend}'))
        
        # Clean up
        cache.delete(test_key)
        
        self.stdout.write(self.style.SUCCESS('\n✅ Cache testing complete!'))
