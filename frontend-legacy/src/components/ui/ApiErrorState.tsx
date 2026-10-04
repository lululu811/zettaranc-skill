import Card from './Card';
import Button from './Button';

interface Props {
  message?: string;
  onRetry?: () => void;
}

export default function ApiErrorState({ message, onRetry }: Props) {
  return (
    <Card>
      <div className="flex flex-col items-center text-center py-8">
        <div className="text-3xl mb-3 text-accent-red opacity-70">⚠</div>
        <div className="text-sm font-bold text-text-primary mb-1">数据加载失败</div>
        <div className="text-xs text-text-muted mb-4 max-w-sm">{message || '后端服务暂时不可用,请检查网络或稍后重试。'}</div>
        {onRetry && <Button onClick={onRetry}>重试</Button>}
      </div>
    </Card>
  );
}
