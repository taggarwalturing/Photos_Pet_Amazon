import { useState } from 'react';

// ── Category definitions ──
const CATEGORY_GUIDE = [
  {
    name: 'Lighting Variation',
    description: 'Describes the lighting conditions present in the photograph.',
    options: [
      { label: 'Well-lit conditions (typical)', desc: 'Evenly lit with clear visibility — standard indoor or natural outdoor lighting.' },
      { label: 'Harsh outdoor sunlight with shadows', desc: 'Bright direct sunlight creating strong shadows and high contrast areas.' },
      { label: 'Low light conditions', desc: 'Dark or dimly lit environment; the image may appear noisy or grainy.' },
      { label: 'Dusk-dawn lighting', desc: 'Warm, dim natural light captured during twilight hours (sunrise/sunset).' },
      { label: 'None of the Above', desc: 'The lighting does not match any of the above descriptions.' },
    ],
  },
  {
    name: 'Angle & Perspective Variation',
    description: 'The camera angle and perspective relative to the pet.',
    options: [
      { label: 'Front-facing at eye level (typical)', desc: 'Camera is at the pet\'s eye level, facing it directly.' },
      { label: 'Ground-level view', desc: 'Camera placed very low — at or near ground level looking up or across.' },
      { label: 'Top-down view', desc: 'Camera looking straight down from above (bird\'s-eye view).' },
      { label: 'Partial view (head only)', desc: 'Only the pet\'s head/face is visible; the body is not shown.' },
      { label: 'No head showing', desc: 'The pet\'s head is completely out of frame.' },
      { label: 'None of the Above', desc: 'The angle does not match any of the above descriptions.' },
    ],
  },
  {
    name: 'Environmental Context Variation',
    description: 'The setting or environment where the pet is photographed.',
    options: [
      { label: 'Indoor setting (typical)', desc: 'Standard indoor environment such as a home, room, or floor.' },
      { label: 'Yard with a complex background', desc: 'Outdoor yard with busy or cluttered background elements.' },
      { label: 'Outdoor dirt road', desc: 'Outside on an unpaved or dirt/gravel surface.' },
      { label: 'Snow environment', desc: 'Snowy outdoor setting with visible snow.' },
      { label: 'Vet clinic', desc: 'Veterinary office, clinic, or medical setting.' },
      { label: 'In car-carrier', desc: 'Pet is inside a car, travel carrier, or crate.' },
      { label: 'None of the Above', desc: 'The environment does not match any of the above descriptions.' },
    ],
  },
  {
    name: 'Occlusion & Partial Visibility',
    description: 'How much of the pet is visible versus hidden or obstructed.',
    options: [
      { label: 'Full-body, unobstructed (typical)', desc: 'The entire pet body is visible with no obstruction.' },
      { label: 'Behind furniture (face only)', desc: 'Pet is behind furniture with only its face peeking out.' },
      { label: 'Partially hidden under a blanket', desc: 'Part of the pet is covered by a blanket, towel, or fabric.' },
      { label: 'Peeking out of box-carrier', desc: 'Pet\'s head/body is partially visible from inside a box or carrier.' },
      { label: 'Toy obscuring part of body', desc: 'A toy or object blocks part of the pet\'s body from view.' },
      { label: 'None of the Above', desc: 'The occlusion does not match any of the above descriptions.' },
    ],
  },
  {
    name: 'Activity & Motion',
    description: 'What the pet is doing at the moment the photo was taken.',
    options: [
      { label: 'Sitting still-posed (typical)', desc: 'Pet is sitting, standing still, or in a posed position.' },
      { label: 'Running with motion blur', desc: 'Pet is running or in motion — the image may show motion blur.' },
      { label: 'Jumping to catch toy', desc: 'Pet is mid-air or leaping to catch something.' },
      { label: 'Playing with another pet', desc: 'Pet is interacting or playing with another animal.' },
      { label: 'Eating-drinking', desc: 'Pet is eating food or drinking water.' },
      { label: 'Sleeping-curled up', desc: 'Pet is sleeping, resting, or curled up.' },
      { label: 'None of the Above', desc: 'The activity does not match any of the above descriptions.' },
    ],
  },
  {
    name: 'Multi-Pet Disambiguation',
    description: 'Number and similarity of pets visible in the image.',
    options: [
      { label: 'Single pet (typical)', desc: 'Only one pet is present in the image.' },
      { label: 'Two similar-looking pets together', desc: 'Two pets that look alike are in the same image.' },
      { label: 'Three pets of same breed', desc: 'Three pets of the same or similar breed appear together.' },
      { label: 'Pet with breed lookalike', desc: 'One main pet alongside another pet of a similar breed appearance.' },
      { label: 'None of the Above', desc: 'The scenario does not match any of the above descriptions.' },
    ],
  },
];

export default function CategoryGuideModal({ isOpen, onClose }) {
  const [expandedIdx, setExpandedIdx] = useState(null);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-indigo-50 to-purple-50 flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              📖 Category Guide
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">Definitions for each category and its options</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-200/60 transition text-gray-500 cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {CATEGORY_GUIDE.map((cat, idx) => {
            const isExpanded = expandedIdx === idx;
            return (
              <div key={cat.name} className="border border-gray-200 rounded-xl overflow-hidden">
                <button
                  onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition cursor-pointer text-left"
                >
                  <div>
                    <h3 className="font-semibold text-gray-900 text-sm">{cat.name}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">{cat.description}</p>
                  </div>
                  <svg
                    className={`w-5 h-5 text-gray-400 transition-transform shrink-0 ml-2 ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {isExpanded && (
                  <div className="border-t border-gray-200 px-4 py-3 bg-gray-50/50 space-y-2.5">
                    {cat.options.map((opt) => (
                      <div key={opt.label} className="flex gap-3 items-start">
                        <div className="w-2 h-2 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
                        <div>
                          <span className="font-medium text-sm text-gray-800">{opt.label}</span>
                          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{opt.desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 shrink-0 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition cursor-pointer"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
