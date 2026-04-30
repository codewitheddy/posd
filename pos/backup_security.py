"""
Backup encryption and integrity utilities
"""
import os
import hashlib
import subprocess
import logging
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupEncryption:
    """Handle GPG encryption/decryption of backup files"""
    
    GPG_RECIPIENT = getattr(settings, 'BACKUP_GPG_RECIPIENT', None)
    GPG_PASSPHRASE = getattr(settings, 'BACKUP_GPG_PASSPHRASE', None)
    ENABLE_ENCRYPTION = getattr(settings, 'BACKUP_ENABLE_ENCRYPTION', True)
    
    @classmethod
    def encrypt_file(cls, file_path):
        """
        Encrypt backup file with GPG.
        Creates file_path.gpg and returns path to encrypted file.
        """
        if not cls.ENABLE_ENCRYPTION:
            return file_path
            
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Backup file not found: {file_path}")
        
        encrypted_path = f"{file_path}.gpg"
        
        try:
            if cls.GPG_RECIPIENT:
                # Public key encryption (preferred)
                cmd = ['gpg', '--trust-model', 'always', 
                       '-e', '--recipient', cls.GPG_RECIPIENT,
                       '--output', encrypted_path, file_path]
            elif cls.GPG_PASSPHRASE:
                # Symmetric encryption with passphrase
                cmd = ['gpg', '--symmetric', '--cipher-algo', 'AES256',
                       '--output', encrypted_path, file_path]
                env = os.environ.copy()
                env['GPG_PASSPHRASE'] = cls.GPG_PASSPHRASE
            else:
                logger.warning("GPG encryption disabled: no recipient or passphrase configured")
                return file_path
            
            # Run GPG encryption
            env = os.environ.copy() if cls.GPG_PASSPHRASE else {}
            if cls.GPG_PASSPHRASE:
                env['GPG_PASSPHRASE'] = cls.GPG_PASSPHRASE
                
            result = subprocess.run(cmd, env=env if env else None, 
                                  capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise RuntimeError(f"GPG encryption failed: {result.stderr}")
            
            # Remove unencrypted original
            if os.path.exists(encrypted_path):
                os.remove(file_path)
                logger.info(f"Encrypted backup: {encrypted_path}")
                return encrypted_path
            else:
                raise RuntimeError("Encryption produced no output file")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("GPG encryption timed out")
        except Exception as e:
            logger.error(f"Backup encryption failed: {e}")
            raise
    
    @classmethod
    def decrypt_file(cls, encrypted_path, output_path=None):
        """
        Decrypt GPG backup file.
        Returns path to decrypted file.
        """
        if not encrypted_path.endswith('.gpg'):
            # Not encrypted
            return encrypted_path
        
        if not os.path.exists(encrypted_path):
            raise FileNotFoundError(f"Encrypted backup not found: {encrypted_path}")
        
        if output_path is None:
            output_path = encrypted_path[:-4]  # Remove .gpg extension
        
        try:
            cmd = ['gpg', '--output', output_path, '--decrypt', encrypted_path]
            
            env = os.environ.copy()
            if cls.GPG_PASSPHRASE:
                env['GPG_PASSPHRASE'] = cls.GPG_PASSPHRASE
            
            result = subprocess.run(cmd, env=env, capture_output=True, 
                                  text=True, timeout=300)
            
            if result.returncode != 0:
                raise RuntimeError(f"GPG decryption failed: {result.stderr}")
            
            if not os.path.exists(output_path):
                raise RuntimeError("Decryption produced no output file")
            
            logger.info(f"Decrypted backup: {output_path}")
            return output_path
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("GPG decryption timed out")
        except Exception as e:
            logger.error(f"Backup decryption failed: {e}")
            raise


class BackupIntegrity:
    """Handle backup checksum and integrity verification"""
    
    @staticmethod
    def calculate_sha256(file_path, chunk_size=8192):
        """Calculate SHA-256 checksum of file"""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                sha256.update(data)
        
        return sha256.hexdigest()
    
    @classmethod
    def create_checksum_file(cls, backup_file):
        """
        Create .sha256 checksum file for backup.
        Returns path to checksum file.
        """
        checksum = cls.calculate_sha256(backup_file)
        checksum_file = f"{backup_file}.sha256"
        
        with open(checksum_file, 'w') as f:
            f.write(f"{checksum}  {os.path.basename(backup_file)}\n")
        
        logger.info(f"Created checksum: {checksum_file}")
        return checksum_file
    
    @classmethod
    def verify_checksum(cls, backup_file):
        """
        Verify backup file against .sha256 checksum.
        Returns True if valid, raises exception if invalid.
        """
        checksum_file = f"{backup_file}.sha256"
        
        if not os.path.exists(checksum_file):
            logger.warning(f"No checksum file found: {checksum_file}")
            return False
        
        # Read stored checksum
        with open(checksum_file, 'r') as f:
            stored_checksum = f.read().split()[0]
        
        # Calculate current checksum
        current_checksum = cls.calculate_sha256(backup_file)
        
        if stored_checksum != current_checksum:
            raise ValueError(
                f"Checksum mismatch for {backup_file}:\n"
                f"Expected: {stored_checksum}\n"
                f"Got: {current_checksum}"
            )
        
        logger.info(f"Checksum verified: {backup_file}")
        return True


def enable_backup_encryption(gpg_recipient=None, gpg_passphrase=None):
    """Enable GPG encryption for backups"""
    if gpg_recipient:
        os.environ['BACKUP_GPG_RECIPIENT'] = gpg_recipient
    if gpg_passphrase:
        os.environ['BACKUP_GPG_PASSPHRASE'] = gpg_passphrase
