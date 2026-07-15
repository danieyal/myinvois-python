<?php
/**
 * Phase 4 fixture generator — emits the byte-for-byte golden SIGNED-XML and
 * SIGNED-JSON outputs that the myinvois-python Phase 4 implementation must reproduce.
 *
 * Mirrors the same Invoice wiring as tests/unit/test_envelope_builder.py
 * `_sample_invoice()` (the source of `golden_invoice_unsigned.xml`).
 *
 * Signing-time is hard-locked to 2024-01-15T10:00:00Z so the fixtures are
 * reproducible. We achieve this by subclassing {Xml,Json}DocumentBuilder and
 * overriding `createSignature` to inline the entire pipeline (a single line
 * differs: `new DateTime('now', UTC)` becomes `new DateTime('2024-01-15 …')`).
 *
 * Knock-on doc change: `Invoice::setInvoiceTypeCode($typeCode, '1.1')` is called
 * after signing to advertise "signed-1.1" — same as the PHP SDK's bundled
 * `CreateDocumentExample` does when `$includeSignature === true`.
 *
 * Invocation:
 *   cd /root/workspace/project/<hash>  (this repo root)
 *   php scripts/gen_signed_golden.php
 *
 * Writes:
 *   tests/fixtures/golden_invoice_signed.xml
 *   tests/fixtures/golden_invoice_signed.json
 *
 * NB: This script MUST run from a working tree that has the PHP SDK vendored at
 *     /tmp/phpsdk (composer-installed during Phase 3c). The autoloader path
 *     below is hard-pinned.
 */

require '/tmp/phpsdk/vendor/autoload.php';

use Klsheng\Myinvois\Ubl\Builder\XmlDocumentBuilder;
use Klsheng\Myinvois\Ubl\Builder\JsonDocumentBuilder;
use Klsheng\Myinvois\Ubl\Builder\AbstractDocumentBuilder;
use Klsheng\Myinvois\Ubl\Constant\UblAttributes;
use Klsheng\Myinvois\Ubl\Constant\UblSpecifications;
use Klsheng\Myinvois\Ubl\Constant\CurrencyCodes;
use Klsheng\Myinvois\Ubl\Constant\CountryCodes;
use Klsheng\Myinvois\Ubl\Invoice;
use Klsheng\Myinvois\Ubl\Address;
use Klsheng\Myinvois\Ubl\AddressLine;
use Klsheng\Myinvois\Ubl\Country;
use Klsheng\Myinvois\Ubl\Contact;
use Klsheng\Myinvois\Ubl\Party;
use Klsheng\Myinvois\Ubl\PartyIdentification;
use Klsheng\Myinvois\Ubl\LegalEntity;
use Klsheng\Myinvois\Ubl\AccountingParty;
use Klsheng\Myinvois\Ubl\TaxScheme;
use Klsheng\Myinvois\Ubl\TaxCategory;
use Klsheng\Myinvois\Ubl\TaxSubTotal;
use Klsheng\Myinvois\Ubl\TaxTotal;
use Klsheng\Myinvois\Ubl\AllowanceCharge;
use Klsheng\Myinvois\Ubl\LegalMonetaryTotal;
use Klsheng\Myinvois\Ubl\Item;
use Klsheng\Myinvois\Ubl\CommodityClassification;
use Klsheng\Myinvois\Ubl\Price;
use Klsheng\Myinvois\Ubl\ItemPriceExtension;
use Klsheng\Myinvois\Ubl\InvoiceLine;
use Klsheng\Myinvois\Ubl\Generator;
use Klsheng\Myinvois\Ubl\Extension\IssuerSerial;
use Klsheng\Myinvois\Ubl\Extension\Signature;
use Klsheng\Myinvois\Ubl\Extension\SignInfo;
use Klsheng\Myinvois\Ubl\Extension\SignInfoReference;
use Klsheng\Myinvois\Ubl\Extension\SignInfoTransform;
use Klsheng\Myinvois\Ubl\Extension\KeyInfo;
use Klsheng\Myinvois\Ubl\Extension\KeyInfoX509Data;
use Klsheng\Myinvois\Ubl\Extension\SignatureObject;
use Klsheng\Myinvois\Ubl\Extension\QualifyingProperties;
use Klsheng\Myinvois\Ubl\Extension\SignedProperties;
use Klsheng\Myinvois\Ubl\Extension\SignedSignatureProperties;
use Klsheng\Myinvois\Ubl\Extension\SigningCertificate;
use Klsheng\Myinvois\Ubl\Extension\CertDigest;
use Klsheng\Myinvois\Ubl\Extension\UBLExtensions;
use Klsheng\Myinvois\Ubl\Extension\UBLExtensionItem;
use Klsheng\Myinvois\Ubl\Extension\UBLDocumentSignatures;
use Klsheng\Myinvois\Ubl\Extension\SignatureInformation;
use Klsheng\Myinvois\Helper\MyInvoisHelper;

const FIXED_SIGNING_TIME = '2024-01-15 10:00:00';

/** Same sample invoice shape as tests/unit/test_envelope_builder.py::_sample_invoice(). */
function buildSampleInvoice(string $invoiceTypeCode = '01', bool $signed = false): Invoice {
    $issueDateTime = new \DateTime('2024-06-14 09:30:00', new \DateTimeZone('UTC'));

    $invoice = new Invoice();
    $invoice->setId('INV-0001');
    $invoice->setIssueDateTime($issueDateTime);
    $invoice->setInvoiceTypeCode($invoiceTypeCode, $signed ? '1.1' : '1.0');
    $invoice->setDocumentCurrencyCode('MYR');

    // Supplier
    $supplierAddress = (new Address())
        ->setCityName('Kuala Lumpur')
        ->setPostalZone('50480')
        ->setCountrySubentityCode('14')
        ->addAddressLine((new AddressLine())->setLine('Lot 66, Bangunan Merdeka'))
        ->addAddressLine((new AddressLine())->setLine('Persiaran Jaya'))
        ->setCountry((new Country())->setIdentificationCode('MYS'));
    $supplierParty = new AccountingParty();
    $supplierParty->setParty(new Party());
    $supplierParty->setAdditionalAccountID('CPT-CCN-W-211111-KL-000002', 'CertEX');
    $supplierParty->getParty()
        ->setIndustryClassificationCode('01111', 'Agriculture')
        ->setPartyIdentification((new PartyIdentification())->setId('C2584563222', 'TIN'))
        ->setPostalAddress($supplierAddress)
        ->setLegalEntity((new LegalEntity())->setRegistrationName('AMS Setia Jaya Sdn. Bhd.'))
        ->setContact((new Contact())->setTelephone('+60123456789')->setElectronicMail('general.ams@supplier.com'));
    $invoice->setAccountingSupplierParty($supplierParty);

    // Customer
    $customerAddress = (new Address())
        ->setCityName('Kuala Lumpur')
        ->setPostalZone('50480')
        ->setCountrySubentityCode('14')
        ->addAddressLine((new AddressLine())->setLine('Lot 66, Bangunan Merdeka'))
        ->addAddressLine((new AddressLine())->setLine('Persiaran Jaya'))
        ->setCountry((new Country())->setIdentificationCode('MYS'));
    $customerParty = new AccountingParty();
    $customerParty->setParty(new Party());
    $customerParty->getParty()
        ->setPartyIdentification((new PartyIdentification())->setId('C2584563200', 'TIN'))
        ->setPostalAddress($customerAddress)
        ->setLegalEntity((new LegalEntity())->setRegistrationName('Hebat Group'))
        ->setContact((new Contact())->setTelephone('+60123456789')->setElectronicMail('name@buyer.com'));
    $invoice->setAccountingCustomerParty($customerParty);

    // Top-level TaxTotal
    $documentTaxScheme = new TaxScheme();
    $documentTaxScheme->setId('OTH');
    $documentTaxCategory = (new TaxCategory())->setId('01')->setTaxScheme($documentTaxScheme);
    $documentTaxSubtotal = (new TaxSubTotal())
        ->setTaxableAmount('87.63', 'MYR')
        ->setTaxAmount('87.63', 'MYR')
        ->setTaxCategory($documentTaxCategory);
    $documentTaxTotal = (new TaxTotal())
        ->setTaxAmount('87.63', 'MYR')
        ->addTaxSubtotal($documentTaxSubtotal);
    $invoice->setTaxTotal($documentTaxTotal);

    // LegalMonetaryTotal
    $legalMonetaryTotal = (new LegalMonetaryTotal())
        ->setLineExtensionAmount('1436.50', 'MYR')
        ->setTaxExclusiveAmount('1436.50', 'MYR')
        ->setTaxInclusiveAmount('1436.50', 'MYR')
        ->setAllowanceTotalAmount('1436.50', 'MYR')
        ->setChargeTotalAmount('1436.50', 'MYR')
        ->setPayableRoundingAmount('0.30', 'MYR')
        ->setPayableAmount('1436.50', 'MYR');
    $invoice->setLegalMonetaryTotal($legalMonetaryTotal);

    // Invoice line + line TaxTotal + Item + Price + ItemPriceExtension + AllowanceCharge ×2
    $lineTaxScheme = new TaxScheme();
    $lineTaxScheme->setId('OTH');
    $lineTaxCategory = (new TaxCategory())
        ->setId('01')
        ->setPercent('10.00')
        ->setTaxExemptionReason('Exempt New Means of Transport')
        ->setTaxScheme($lineTaxScheme);
    $lineTaxSubtotal = (new TaxSubTotal())
        ->setTaxableAmount('1436.50', 'MYR')
        ->setTaxAmount('14.61', 'MYR')
        ->setPercent('10.00')
        ->setTaxCategory($lineTaxCategory);
    $lineTaxTotal = (new TaxTotal())
        ->setTaxAmount('14.61', 'MYR')
        ->addTaxSubtotal($lineTaxSubtotal);

    $item = (new Item())
        ->setDescription('螺丝')
        ->setCommodityClassification(
            (new CommodityClassification())->setItemClassificationCode('011', 'CLASS')
        );
    $price = (new Price())->setPriceAmount('17.00', 'MYR');
    $itemPriceExtension = (new ItemPriceExtension())->setAmount('100.00', 'MYR');

    $line = (new InvoiceLine())
        ->setId('1234')
        ->setInvoicedQuantity('1.00', 'C62')
        ->setLineExtensionAmount('1436.50', 'MYR')
        ->addAllowanceCharge(
            (new AllowanceCharge())
                ->setChargeIndicator(false)
                ->setAllowanceChargeReason('Sample Description 2')
                ->setMultiplierFactorNumeric('0.15')
                ->setAmount('100.00', 'MYR')
        )
        ->addAllowanceCharge(
            (new AllowanceCharge())
                ->setChargeIndicator(true)
                ->setAllowanceChargeReason('Service charge')
                ->setMultiplierFactorNumeric('0.10')
                ->setAmount('100.00', 'MYR')
        )
        ->setTaxTotal($lineTaxTotal)  // line-level (InvoiceLine::setTaxTotal)
        ->setItem($item)
        ->setPrice($price)
        ->setItemPriceExtension($itemPriceExtension);
    $invoice->addInvoiceLine($line);

    return $invoice;
}

/**
 * XmlDocumentBuilder with locked signing time.
 *
 * We re-implement `createSignature` because the parent marks `setSignatureObject`
 * private and we have no injection seam. The whole sequence mirrors the parent
 * (`AbstractDocumentBuilder::createSignature`) bit-for-bit except for the
 * `new DateTime('now', UTC)` → `new DateTime(FIXED_SIGNING_TIME, UTC)` swap.
 */
class DeterministicXmlDocumentBuilder extends XmlDocumentBuilder {
    public function createSignature($certFilePath, $certPrivateKeyFilePath, $passphrase = null) {
        if (empty($certFilePath)) throw new InvalidArgumentException('certFilePath is empty');
        if (empty($certPrivateKeyFilePath) && empty($passphrase)) throw new InvalidArgumentException('certPrivateKeyFilePath and passphrase is empty');

        $certContent = file_get_contents($certFilePath);
        $ext = pathinfo($certFilePath, PATHINFO_EXTENSION);
        if ($ext === 'p12' || $ext === 'pfx') {
            if (!openssl_pkcs12_read($certContent, $certs, $passphrase)) {
                throw new InvalidArgumentException('certFilePath is invalid');
            }
            $certContent = $certs['cert'];
            $certPrivateKeyContent = $certs['pkey'];
        } else {
            $certPrivateKeyContent = file_get_contents($certPrivateKeyFilePath);
        }

        $data = openssl_x509_parse($certContent);
        $issuerArray = $data['issuer'];

        $issuerKeys = ['CN', 'E', 'OU', 'O', 'C'];
        foreach ($issuerKeys as $issuerKey) {
            if (array_key_exists($issuerKey, $issuerArray)) {
                $issuerValue = $issuerArray[$issuerKey];
                unset($issuerArray[$issuerKey]);
                $issuerArray = array_merge($issuerArray, [$issuerKey => $issuerValue]);
            }
        }
        $issuerName = urldecode(http_build_query($issuerArray, '', ', '));
        $serialNumber = $data['serialNumber'];

        $issuerSerial = (new IssuerSerial())->setIssuerName($issuerName)->setSerialNumber($serialNumber);

        $signature = new Signature();
        $signature->setAttributes(['Id' => 'signature']);

        $documentString = $this->build();
        $documentHash = MyInvoisHelper::getHash($documentString, true);

        // Step 4: SignatureValue
        openssl_sign($documentString, $signatureValue, $certPrivateKeyContent, OPENSSL_ALGO_SHA256);
        $signature->setSignatureValue(base64_encode($signatureValue));

        // Step 5/6: SignatureObject (SigningCertificate/CertDigest + SignedSignatureProperties)
        $signingTime = new \DateTime(FIXED_SIGNING_TIME, new \DateTimeZone('UTC'));
        $certRaw = $this->getRawContent($certContent);
        $certHash = MyInvoisHelper::getHash(base64_decode($certRaw), true);
        $certDigest = (new CertDigest())->setDigestValue(base64_encode($certHash));
        $signingCertificate = (new SigningCertificate())->setCertDigest($certDigest)->setIssuerSerial($issuerSerial);
        $signedSignatureProperties = (new SignedSignatureProperties())->setSigningTime($signingTime)->setSigningCertificate($signingCertificate);
        $signedProperties = (new SignedProperties())->setSignedSignatureProperties($signedSignatureProperties);
        $qualifyingProperties = (new QualifyingProperties())->setSignedProperties($signedProperties);
        $signatureObject = (new SignatureObject())->setQualifyingProperties($qualifyingProperties);
        $signature->setObject($signatureObject);

        // KeyInfo
        $x509Data = (new KeyInfoX509Data())->setX509Certificate($certRaw)->setIssuerSerial($issuerSerial);
        $signature->setKeyInfo((new KeyInfo())->setX509Data($x509Data));

        // SignInfo + 2 references
        $signedInfo = new SignInfo();
        $reference = new SignInfoReference();
        $reference->setAttributes(['Id' => 'id-doc-signed-data', 'URI' => '']);
        $reference->setDigestValue(base64_encode($documentHash));
        $reference->addTransform((new SignInfoTransform())->setXPath('not(//ancestor-or-self::ext:UBLExtensions)'));
        $reference->addTransform((new SignInfoTransform())->setXPath('not(//ancestor-or-self::cac:Signature)'));
        $reference->addTransform((new SignInfoTransform())->setAttributes([UblAttributes::ALGORITHM => 'http://www.w3.org/2006/12/xml-c14n11']));
        $signedInfo->addReference($reference);

        $propsDigestHash = $this->getPropsDigestHash($signature);
        $reference = new SignInfoReference();
        $reference->setAttributes(['Type' => 'http://uri.etsi.org/01903/v1.3.2#SignedProperties', 'URI' => '#id-xades-signed-props']);
        $reference->setDigestValue(base64_encode($propsDigestHash));
        $signedInfo->addReference($reference);
        $signature->setSignInfo($signedInfo);

        $information = (new SignatureInformation())->setSignature($signature);
        $sign = (new UBLDocumentSignatures())->setSignatureInformation($information);
        $ublExtensionItem = (new UBLExtensionItem())->setContent($sign);
        $ublExtensions = (new UBLExtensions())->addUBLExtensionItem($ublExtensionItem);

        $invoice = $this->getDocument();
        $invoice->setInvoiceTypeCode($invoice->getInvoiceTypeCode(), '1.1');
        $invoice->setUBLExtensions($ublExtensions);
        return $this;
    }

    private function getRawContent($content)
    {
        $content = str_replace(array("\r"), '', $content);
        $keyArray = explode("\n", $content);
        unset($keyArray[0]);
        $lastKey = key(array_slice($keyArray, -1, 1, true));
        while (empty($keyArray[$lastKey])) {
            unset($keyArray[$lastKey]);
            $lastKey = key(array_slice($keyArray, -1, 1, true));
        }
        unset($keyArray[$lastKey]);
        return implode('', $keyArray);
    }
}

// JSON-flavoured variant — same swap, single-signature embed path.
class DeterministicJsonDocumentBuilder extends JsonDocumentBuilder {
    public function createSignature($certFilePath, $certPrivateKeyFilePath, $passphrase = null) {
        if (empty($certFilePath)) throw new InvalidArgumentException('certFilePath is empty');
        if (empty($certPrivateKeyFilePath) && empty($passphrase)) throw new InvalidArgumentException('certPrivateKeyFilePath and passphrase is empty');

        $certContent = file_get_contents($certFilePath);
        $ext = pathinfo($certFilePath, PATHINFO_EXTENSION);
        if ($ext === 'p12' || $ext === 'pfx') {
            if (!openssl_pkcs12_read($certContent, $certs, $passphrase)) throw new InvalidArgumentException('certFilePath is invalid');
            $certContent = $certs['cert'];
            $certPrivateKeyContent = $certs['pkey'];
        } else {
            $certPrivateKeyContent = file_get_contents($certPrivateKeyFilePath);
        }

        $data = openssl_x509_parse($certContent);
        $issuerArray = $data['issuer'];
        $issuerKeys = ['CN', 'E', 'OU', 'O', 'C'];
        foreach ($issuerKeys as $issuerKey) {
            if (array_key_exists($issuerKey, $issuerArray)) {
                $issuerValue = $issuerArray[$issuerKey];
                unset($issuerArray[$issuerKey]);
                $issuerArray = array_merge($issuerArray, [$issuerKey => $issuerValue]);
            }
        }
        $issuerName = urldecode(http_build_query($issuerArray, '', ', '));
        $serialNumber = $data['serialNumber'];

        $issuerSerial = (new IssuerSerial())->setIssuerName($issuerName)->setSerialNumber($serialNumber);

        $signature = new Signature();
        $signature->setAttributes(['Id' => 'signature']);

        $documentString = $this->build();
        $documentHash = MyInvoisHelper::getHash($documentString, true);

        openssl_sign($documentString, $signatureValue, $certPrivateKeyContent, OPENSSL_ALGO_SHA256);
        $signature->setSignatureValue(base64_encode($signatureValue));

        $signingTime = new \DateTime(FIXED_SIGNING_TIME, new \DateTimeZone('UTC'));
        $certRaw = $this->getRawContent($certContent);
        $certHash = MyInvoisHelper::getHash(base64_decode($certRaw), true);
        $certDigest = (new CertDigest())->setDigestValue(base64_encode($certHash));
        $signingCertificate = (new SigningCertificate())->setCertDigest($certDigest)->setIssuerSerial($issuerSerial);
        $signedSignatureProperties = (new SignedSignatureProperties())->setSigningTime($signingTime)->setSigningCertificate($signingCertificate);
        $signedProperties = (new SignedProperties())->setSignedSignatureProperties($signedSignatureProperties);
        $qualifyingProperties = (new QualifyingProperties())->setSignedProperties($signedProperties);
        $signatureObject = (new SignatureObject())->setQualifyingProperties($qualifyingProperties);
        $signature->setObject($signatureObject);

        $x509Data = (new KeyInfoX509Data())->setX509Certificate($certRaw)->setIssuerSerial($issuerSerial);
        $signature->setKeyInfo((new KeyInfo())->setX509Data($x509Data));

        $signedInfo = new SignInfo();
        $reference = new SignInfoReference();
        $reference->setAttributes(['Id' => 'id-doc-signed-data', 'URI' => '']);
        $reference->setDigestValue(base64_encode($documentHash));
        $reference->addTransform((new SignInfoTransform())->setXPath('not(//ancestor-or-self::ext:UBLExtensions)'));
        $reference->addTransform((new SignInfoTransform())->setXPath('not(//ancestor-or-self::cac:Signature)'));
        $reference->addTransform((new SignInfoTransform())->setAttributes([UblAttributes::ALGORITHM => 'http://www.w3.org/2006/12/xml-c14n11']));
        $signedInfo->addReference($reference);

        $propsDigestHash = $this->getPropsDigestHash($signature);
        $reference = new SignInfoReference();
        $reference->setAttributes(['Type' => 'http://uri.etsi.org/01903/v1.3.2#SignedProperties', 'URI' => '#id-xades-signed-props']);
        $reference->setDigestValue(base64_encode($propsDigestHash));
        $signedInfo->addReference($reference);
        $signature->setSignInfo($signedInfo);

        $information = (new SignatureInformation())->setSignature($signature);
        $sign = (new UBLDocumentSignatures())->setSignatureInformation($information);
        $ublExtensionItem = (new UBLExtensionItem())->setContent($sign);
        $ublExtensions = (new UBLExtensions())->addUBLExtensionItem($ublExtensionItem);

        $invoice = $this->getDocument();
        $invoice->setInvoiceTypeCode($invoice->getInvoiceTypeCode(), '1.1');
        $invoice->setUBLExtensions($ublExtensions);
        return $this;
    }

    private function getRawContent($content)
    {
        $content = str_replace(array("\r"), '', $content);
        $keyArray = explode("\n", $content);
        unset($keyArray[0]);
        $lastKey = key(array_slice($keyArray, -1, 1, true));
        while (empty($keyArray[$lastKey])) {
            unset($keyArray[$lastKey]);
            $lastKey = key(array_slice($keyArray, -1, 1, true));
        }
        unset($keyArray[$lastKey]);
        return implode('', $keyArray);
    }
}

// ----- Build + write fixtures -------------------------------------------------

$certPath = __DIR__ . '/../tests/fixtures/cert/dummy_signing_cert.pem';
$keyPath  = __DIR__ . '/../tests/fixtures/cert/dummy_signing_key.pem';

$xmlInvoice = buildSampleInvoice('01', false);  // signed=false on the first build() (listVersionID stays 1.0 there)
$xmlBuilder = new DeterministicXmlDocumentBuilder();
$xmlBuilder->setDocument($xmlInvoice);
$xmlBuilder->createSignature($certPath, $keyPath);
$signedXml = $xmlBuilder->build();

$jsonInvoice = buildSampleInvoice('01', false);
$jsonBuilder = new DeterministicJsonDocumentBuilder();
$jsonBuilder->setDocument($jsonInvoice);
$jsonBuilder->createSignature($certPath, $keyPath);
$signedJson = $jsonBuilder->build();

$xmlOut = __DIR__ . '/../tests/fixtures/golden_invoice_signed.xml';
$jsonOut = __DIR__ . '/../tests/fixtures/golden_invoice_signed.json';
file_put_contents($xmlOut, $signedXml);
file_put_contents($jsonOut, $signedJson);

echo "Wrote $xmlOut (" . strlen($signedXml) . " bytes)" . PHP_EOL;
echo "Wrote $jsonOut (" . strlen($signedJson) . " bytes)" . PHP_EOL;
echo "XML md5:  " . md5($signedXml) . PHP_EOL;
echo "JSON md5: " . md5($signedJson) . PHP_EOL;
