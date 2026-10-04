interface Props {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  text?: string;
}

const sizeMap = {
  sm: 'w-4 h-4 border-2',
  md: 'w-6 h-6 border-2',
  lg: 'w-10 h-10 border-[3px]',
  xl: 'w-16 h-16 border-4',
};

export default function LoadingSpinner({ size = 'md', text }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <div className="relative">
        {/* 外圈金色光晕 */}
        <div className={`absolute inset-0 rounded-full bg-accent-gold/20 blur-md animate-pulse ${sizeMap[size]}`} />
        {/* 主 spinner */}
        <div
          className={`relative animate-spin rounded-full border-border border-t-accent-gold border-r-accent-gold/60 ${sizeMap[size]}`}
          style={{ animationDuration: '1s' }}
        />
      </div>
      {text && <div className="text-xs text-text-muted tracking-wider uppercase">{text}</div>}
    </div>
  );
}
