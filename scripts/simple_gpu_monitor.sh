#!/bin/bash

# Simple GPU monitoring script using nvidia-smi (if available)
# This version doesn't require additional Python packages

show_gpu_info() {
    echo "🚀 GPU Status Check"
    echo "========================================"
    
    # Check if nvidia-smi is available
    if command -v nvidia-smi &> /dev/null; then
        echo "✅ NVIDIA GPU detected"
        echo ""
        
        # Show GPU info
        nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits | while IFS=',' read -r name memory_total memory_used memory_free gpu_util temp power; do
            # Trim whitespace
            name=$(echo "$name" | xargs)
            memory_total=$(echo "$memory_total" | xargs)
            memory_used=$(echo "$memory_used" | xargs)
            memory_free=$(echo "$memory_free" | xargs)
            gpu_util=$(echo "$gpu_util" | xargs)
            temp=$(echo "$temp" | xargs)
            power=$(echo "$power" | xargs)
            
            # Calculate memory percentage
            memory_percent=$(echo "scale=1; $memory_used * 100 / $memory_total" | bc 2>/dev/null || echo "0")
            
            echo "   GPU: $name"
            echo "      Utilization: ${gpu_util}%"
            echo "      Memory: ${memory_used}MB / ${memory_total}MB (${memory_percent}%)"
            echo "      Temperature: ${temp}°C"
            if [[ "$power" != "[Not Supported]" ]] && [[ -n "$power" ]]; then
                echo "      Power: ${power}W"
            fi
            echo ""
        done
    else
        echo "❌ nvidia-smi not found"
        echo "   GPU monitoring requires NVIDIA drivers and tools"
    fi
    
    # System info using basic commands
    echo "💻 System Info"
    if command -v nproc &> /dev/null; then
        cpu_cores=$(nproc)
        echo "   CPU Cores: $cpu_cores"
    fi
    
    if [[ -f /proc/meminfo ]]; then
        memory_total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        memory_available_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
        memory_total_gb=$(echo "scale=1; $memory_total_kb / 1024 / 1024" | bc 2>/dev/null || echo "N/A")
        memory_used_kb=$((memory_total_kb - memory_available_kb))
        memory_used_gb=$(echo "scale=1; $memory_used_kb / 1024 / 1024" | bc 2>/dev/null || echo "N/A")
        memory_percent=$(echo "scale=1; $memory_used_kb * 100 / $memory_total_kb" | bc 2>/dev/null || echo "N/A")
        
        echo "   RAM: ${memory_used_gb}GB / ${memory_total_gb}GB (${memory_percent}%)"
    fi
}

monitor_gpu_realtime() {
    echo "📊 Real-time GPU Monitoring"
    echo "Press Ctrl+C to stop"
    echo "========================================"
    
    if ! command -v nvidia-smi &> /dev/null; then
        echo "❌ nvidia-smi not available for real-time monitoring"
        return 1
    fi
    
    while true; do
        timestamp=$(date "+%H:%M:%S")
        
        # Get GPU metrics in a single line
        gpu_line=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits | head -1)
        
        if [[ -n "$gpu_line" ]]; then
            IFS=',' read -r gpu_util memory_used memory_total temp <<< "$gpu_line"
            
            # Trim whitespace
            gpu_util=$(echo "$gpu_util" | xargs)
            memory_used=$(echo "$memory_used" | xargs)
            memory_total=$(echo "$memory_total" | xargs)
            temp=$(echo "$temp" | xargs)
            
            # Calculate memory percentage
            memory_percent=$(echo "scale=1; $memory_used * 100 / $memory_total" | bc 2>/dev/null || echo "0")
            
            # Format memory in GB
            memory_used_gb=$(echo "scale=1; $memory_used / 1024" | bc 2>/dev/null || echo "0")
            memory_total_gb=$(echo "scale=1; $memory_total / 1024" | bc 2>/dev/null || echo "0")
            
            # Temperature icon
            if (( $(echo "$temp >= 80" | bc -l 2>/dev/null || echo "0") )); then
                temp_icon="🔥"
            else
                temp_icon="🌡️"
            fi
            
            # Format with compact, consistent display
            output=$(printf "[%s] GPU:%3s%% | VRAM:%4.1f%%(%4.1fGB) | %s%2s°C" \
                "$timestamp" "$gpu_util" "$memory_percent" "$memory_used_gb" "$temp_icon" "$temp")
            
            # Clear line and print with consistent width
            printf "\r%-70s" "$output"
        else
            output=$(printf "[%s] GPU: N/A" "$timestamp")
            printf "\r%-70s" "$output"
        fi
        
        sleep 1
    done
}

# Main script
case "${1:-info}" in
    "info")
        show_gpu_info
        ;;
    "monitor")
        show_gpu_info
        echo ""
        monitor_gpu_realtime
        ;;
    "help")
        echo "Simple GPU Monitor Usage:"
        echo "  $0 info     # Show current GPU status (default)"
        echo "  $0 monitor  # Real-time monitoring"
        echo "  $0 help     # Show this help"
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac