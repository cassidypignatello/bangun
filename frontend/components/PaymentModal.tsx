'use client';

import { useState } from 'react';
import { PaymentMethod } from '@/lib/types';
import { usePayment } from '@/lib/hooks';

interface PaymentModalProps {
  workerId: string;
  workerName: string;
  unlockPrice: number;
  isOpen: boolean;
  onClose: () => void;
}

export function PaymentModal({
  workerId,
  workerName,
  unlockPrice,
  isOpen,
  onClose,
}: PaymentModalProps) {
  const { loading, error, initiateUnlock } = usePayment();
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod | null>(null);
  // Buyer email: identifies the user for unlock-status checks (interim
  // identity mechanism until real auth — persisted by initiateUnlock).
  const [email, setEmail] = useState('');

  const emailValid = /^\S+@\S+\.\S+$/.test(email.trim());

  const formatPrice = (priceIdr: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
    }).format(priceIdr);
  };

  const handlePayment = async () => {
    if (!selectedMethod || !emailValid) return;
    await initiateUnlock(workerId, selectedMethod, email.trim());
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
          {/* Header */}
          <div className="mb-6">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Unlock Worker Details
            </h2>
            <p className="text-gray-600">
              Get full contact information and negotiation tips for {workerName}
            </p>
          </div>

          {/* Price */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <div className="flex justify-between items-center">
              <span className="text-gray-700">Unlock Price:</span>
              <span className="text-2xl font-bold text-blue-600">
                {formatPrice(unlockPrice)}
              </span>
            </div>
          </div>

          {/* What You Get */}
          <div className="mb-6">
            <h3 className="font-semibold text-gray-900 mb-3">What you&apos;ll get:</h3>
            <ul className="space-y-2 text-sm text-gray-600">
              <li className="flex items-start">
                <span className="text-green-500 mr-2">✓</span>
                Full business contact details (phone, WhatsApp, email)
              </li>
              <li className="flex items-start">
                <span className="text-green-500 mr-2">✓</span>
                Complete address and location information
              </li>
              <li className="flex items-start">
                <span className="text-green-500 mr-2">✓</span>
                AI-powered negotiation script in Bahasa Indonesia
              </li>
              <li className="flex items-start">
                <span className="text-green-500 mr-2">✓</span>
                Fair price guidelines for your project
              </li>
              <li className="flex items-start">
                <span className="text-green-500 mr-2">✓</span>
                All reviews and portfolio photos
              </li>
            </ul>
          </div>

          {/* Buyer Email */}
          <div className="mb-6">
            <label
              htmlFor="unlock-email"
              className="block font-semibold text-gray-900 mb-2"
            >
              Your Email:
            </label>
            <input
              id="unlock-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg focus:border-blue-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-gray-500">
              Used to link this unlock to you so you can access the details later.
            </p>
          </div>

          {/* Payment Method Selection */}
          <div className="mb-6">
            <h3 className="font-semibold text-gray-900 mb-3">Choose Payment Method:</h3>
            <div className="space-y-2">
              <button
                onClick={() => setSelectedMethod(PaymentMethod.GOPAY)}
                className={`w-full p-4 border-2 rounded-lg text-left transition-colors ${
                  selectedMethod === PaymentMethod.GOPAY
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-blue-500 rounded flex items-center justify-center text-white font-bold mr-3">
                      GP
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900">GoPay</div>
                      <div className="text-xs text-gray-600">Instant payment via GoPay</div>
                    </div>
                  </div>
                  {selectedMethod === PaymentMethod.GOPAY && (
                    <span className="text-blue-500 text-xl">✓</span>
                  )}
                </div>
              </button>

              <button
                onClick={() => setSelectedMethod(PaymentMethod.QRIS)}
                className={`w-full p-4 border-2 rounded-lg text-left transition-colors ${
                  selectedMethod === PaymentMethod.QRIS
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-purple-500 rounded flex items-center justify-center text-white font-bold mr-3">
                      QR
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900">QRIS</div>
                      <div className="text-xs text-gray-600">Scan QR code with any e-wallet</div>
                    </div>
                  </div>
                  {selectedMethod === PaymentMethod.QRIS && (
                    <span className="text-blue-500 text-xl">✓</span>
                  )}
                </div>
              </button>

              <button
                onClick={() => setSelectedMethod(PaymentMethod.CREDIT_CARD)}
                className={`w-full p-4 border-2 rounded-lg text-left transition-colors ${
                  selectedMethod === PaymentMethod.CREDIT_CARD
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-green-500 rounded flex items-center justify-center text-white font-bold mr-3">
                      💳
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900">Credit/Debit Card</div>
                      <div className="text-xs text-gray-600">Visa, Mastercard, JCB</div>
                    </div>
                  </div>
                  {selectedMethod === PaymentMethod.CREDIT_CARD && (
                    <span className="text-blue-500 text-xl">✓</span>
                  )}
                </div>
              </button>

              <button
                onClick={() => setSelectedMethod(PaymentMethod.BANK_TRANSFER)}
                className={`w-full p-4 border-2 rounded-lg text-left transition-colors ${
                  selectedMethod === PaymentMethod.BANK_TRANSFER
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-gray-500 rounded flex items-center justify-center text-white font-bold mr-3">
                      🏦
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900">Bank Transfer</div>
                      <div className="text-xs text-gray-600">BCA, Mandiri, BNI, BRI</div>
                    </div>
                  </div>
                  {selectedMethod === PaymentMethod.BANK_TRANSFER && (
                    <span className="text-blue-500 text-xl">✓</span>
                  )}
                </div>
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={onClose}
              disabled={loading}
              className="flex-1 px-4 py-3 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handlePayment}
              disabled={!selectedMethod || !emailValid || loading}
              className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Processing...' : 'Continue to Payment'}
            </button>
          </div>

          {/* Security Notice */}
          <div className="mt-4 text-xs text-center text-gray-500">
            🔒 Secure payment powered by Midtrans
          </div>
        </div>
      </div>
    </div>
  );
}
