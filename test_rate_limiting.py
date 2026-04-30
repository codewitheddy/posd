"""
Test script to verify rate limiting implementation
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.test import Client
from django.urls import reverse
import time

def test_api_rate_limiting():
    """Test API rate limiting"""
    client = Client()

    print("Testing API rate limiting...")

    # Test anonymous API access (should be rate limited)
    api_url = '/api/v1/products/'
    success_count = 0
    rate_limited_count = 0

    for i in range(120):  # Try more than the limit
        response = client.get(api_url)
        if response.status_code == 200:
            success_count += 1
        elif response.status_code == 429:  # Too Many Requests
            rate_limited_count += 1
            print(f"Rate limited after {success_count} requests")
            break
        else:
            print(f"Unexpected status: {response.status_code}")

        if i % 10 == 0:
            print(f"Request {i+1}: Status {response.status_code}")

    print(f"API Test Results: {success_count} successful, {rate_limited_count} rate limited")

def test_auth_rate_limiting():
    """Test authentication rate limiting"""
    client = Client()

    print("\nTesting authentication rate limiting...")

    # Test login rate limiting
    login_url = reverse('login')
    rate_limited_count = 0

    for i in range(5):  # Try more than the 3/minute limit
        response = client.post(login_url, {
            'username': 'test',
            'password': 'wrong'
        })

        if response.status_code == 429:
            rate_limited_count += 1
            print(f"Login rate limited after {i} attempts")
            break

        print(f"Login attempt {i+1}: Status {response.status_code}")

    print(f"Auth Test Results: {rate_limited_count} rate limited")

if __name__ == '__main__':
    test_api_rate_limiting()
    test_auth_rate_limiting()
    print("\nRate limiting tests completed!")