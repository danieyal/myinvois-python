# Test-only signing credentials

The two files in this directory are a **self-signed dummy RSA keypair** generated
specifically for the byte-parity tests in `tests/unit/test_signer_*`:

- `dummy_signing_cert.pem` — self-signed X.509, subject/issuer
  `emailAddress=test@example.com, CN=Test LHDN Signing, OU=MyInvoice Unit, O=Test Org, C=MY`
- `dummy_signing_key.pem` — 4096-bit RSA private key matching the cert above

## Why are they committed?

The Phase 4 signer tests pin against PHP-generated golden fixtures
(`tests/fixtures/golden_invoice_signed.{xml,json}`) which were signed with
*this exact keypair*. Both the signed bytes (md5) and the embedded
`<ds:X509Certificate>` value must remain byte-identical with PHP output, so the
cert/key pair is itself pinned — regenerating a different pair would break
every `XmlSigner`/`JsonSigner` parity assertion.

## Do NOT use in production

These credentials are test-only:

- The certificate is self-signed (subject == issuer) and never chained to any CA.
- It carries the `Test LHDN Signing` Common Name to make accidental production
  use obvious.
- The private key has no password, which would be unacceptable in production.

For real MyInvois signing, supply **both** your own certificate from an
approved Malaysian CA (LHDN does not issue them) **and its matching private
key** through `myinvois.config.CertConfig` — either as
`certificate_path`/`private_key_path`, or as `certificate_bytes`/
`private_key_bytes` from a secret store. Never import from this directory.

## Regenerating (only if you intentionally rebuild the goldens)

1. `openssl req -x509 -newkey rsa:4096 -keyout dummy_signing_key.pem -out \
     dummy_signing_cert.pem -days 3650 -nodes -sha256 \
     -subj "/emailAddress=test@example.com/CN=Test LHDN Signing/OU=MyInvoice Unit/O=Test Org/C=MY"`
2. Re-run `php scripts/gen_signed_golden.php` (needs the PHP SDK at `/tmp/phpsdk`)
   to regenerate `tests/fixtures/golden_invoice_signed.{xml,json}`.
3. Update the expected constants at the top of
   `tests/unit/test_signer_cert.py` (`_EXPECTED_SERIAL_NUMBER`,
   `_EXPECTED_CERT_DIGEST_B64`, `_EXPECTED_ISSUER_NAME`) from the new fixture.
4. Re-run `uv run pytest` to confirm all 260 tests still pass.
