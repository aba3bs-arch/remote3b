#!/usr/bin/env python3
"""
Generate self-signed TLS certificates for AM-CONNECT
Used for WebSocket encryption
"""

import os
import sys
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from datetime import datetime, timedelta
except ImportError:
    print("Please install cryptography: pip install cryptography")
    sys.exit(1)


def generate_self_signed_cert(
    cert_path: str = 'certs/cert.pem',
    key_path: str = 'certs/key.pem',
    hostname: str = 'localhost',
    days_valid: int = 365
):
    """
    Generate self-signed certificate
    
    Args:
        cert_path: Path to save certificate
        key_path: Path to save private key
        hostname: Hostname for certificate
        days_valid: Days the certificate is valid
    """
    
    # Create certs directory
    cert_dir = Path(cert_path).parent
    cert_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating self-signed certificate...")
    print(f"  Hostname: {hostname}")
    print(f"  Valid for: {days_valid} days")
    print(f"  Certificate: {cert_path}")
    print(f"  Key: {key_path}")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"CA"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"AM-CONNECT"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=days_valid)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(hostname),
            x509.DNSName(u'*.localhost'),
            x509.DNSName(u'127.0.0.1'),
        ]),
        critical=False,
    ).add_extension(
        x509.BasicConstraints(ca=False, path_length=None),
        critical=True,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    # Save certificate
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    # Save private key
    with open(key_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Set file permissions
    os.chmod(key_path, 0o600)
    
    print("\n✓ Certificate generated successfully!")
    print(f"\nCertificate Details:")
    print(f"  Subject: {cert.subject}")
    print(f"  Valid From: {cert.not_valid_before}")
    print(f"  Valid Until: {cert.not_valid_after}")
    print(f"  Serial Number: {cert.serial_number}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate self-signed TLS certificates')
    parser.add_argument('--cert', default='certs/cert.pem', help='Certificate path')
    parser.add_argument('--key', default='certs/key.pem', help='Private key path')
    parser.add_argument('--hostname', default='localhost', help='Hostname for certificate')
    parser.add_argument('--days', type=int, default=365, help='Days valid')
    
    args = parser.parse_args()
    
    generate_self_signed_cert(
        cert_path=args.cert,
        key_path=args.key,
        hostname=args.hostname,
        days_valid=args.days
    )
