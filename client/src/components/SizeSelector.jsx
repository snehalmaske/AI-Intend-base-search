export default function SizeSelector({ sizes, selected, onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {sizes.map((size) => (
        <button
          key={size}
          type="button"
          onClick={() => onSelect(size)}
          className={`min-w-[3rem] rounded-full border px-4 py-2 text-sm transition-colors ${
            selected === size
              ? 'border-ink bg-ink text-white'
              : 'border-blush text-ink hover:border-ink'
          }`}
        >
          {size}
        </button>
      ))}
    </div>
  );
}
